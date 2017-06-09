#!/usr/bin/env python
# -*- coding: utf-8 -*-

from bs4 import BeautifulSoup
import requests
import urllib
from pprint import pprint
import boto3


def lambda_handler(event, context):
    """ Route the incoming request based on type (LaunchRequest, IntentRequest,
    etc.) The JSON body of the request is provided in the event parameter.
    """
    print("event.session.application.applicationId=" +
          event['session']['application']['applicationId'])

    """
    Uncomment this if statement and populate with your skill's application ID
    to prevent someone else from configuring a skill that sends requests to
    this function.
    """
    # if (event['session']['application']['applicationId'] != 
    #         os.environ["SKILL_ID"]):
    #     raise ValueError("Invalid Application ID")

    if event['session']['new']:
        on_session_started({'requestId': event['request']['requestId']},
                           event['session'])

    if event['request']['type'] == "LaunchRequest":
        return on_launch(event['request'], event['session'])
    elif event['request']['type'] == "IntentRequest":
        return on_intent(event['request'], event['session'])
    elif event['request']['type'] == "SessionEndedRequest":
        return on_session_ended(event['request'], event['session'])


def on_session_started(session_started_request, session):
    """ Called when the session starts """

    print("on_session_started requestId=" +
          session_started_request['requestId'] +
          ", sessionId=" + session['sessionId'])


def on_launch(launch_request, session):
    """ Called when the user launches the skill without specifying what they
    want
    """

    return get_welcome_response()


def on_intent(intent_request, session):
    """ Called when the user specifies an intent for this skill """

    intent = intent_request['intent']
    intent_name = intent_request['intent']['name']

    # If this is a new session, Mark that it's no longer a new session
    # Then search for a new recipe.    
    if 'attributes' in session.keys() and 'new_session' in session['attributes'].keys() and session['attributes']['new_session'] == True and intent_name == "SearchForRecipe":
        session['attributes']['new_session'] = False
        return alexa_search_for_recipe(intent, session)

    # Search for a recipe
    if intent_name == "SearchForRecipe":
        return alexa_search_for_recipe(intent, session)
    # Once the search results are found, choose a specific recipe
    elif intent_name == "PickRecipeNumber":
        return alexa_pick_recipe_number(intent, session)
    elif intent_name == "NextStep":
        return alexa_next_step(intent, session)
    elif intent_name == "PreviousStep":
        return alexa_previous_step(intent, session)
    elif intent_name == "RepeatStep":
        return alexa_repeat_step(intent, session)
    elif intent_name == "AMAZON.HelpIntent":
        return alexa_help(intent, session)
    elif intent_name == "AMAZON.StopIntent" or intent_name == "AMAZON.CancelIntent":
        return alexa_end_session(intent, session)
    else:
        return alexa_help(intent, session, invalid_intent=True)


def on_session_ended(session_ended_request, session):
    """ Called when the user ends the session.

    Is not called when the skill returns should_end_session=true
    """
    print("on_session_ended requestId=" + session_ended_request['requestId'] +
          ", sessionId=" + session['sessionId'])
    # add cleanup logic here


# --------------- Functions that control the skill's behavior -----------------

def get_welcome_response():
    """ If we wanted to initialize the session to have some attributes we could
    add those here
    """

    session_attributes = {
        'new_session': True
    }
    
    card_title = "Welcome to the Skinnytaste Alexa Skill!"
    speech_output = ('<p>Welcome to the Skinny Taste Alexa skill! You can use this skill to search for and cook along with recipes on the Skinny Taste website. '
                     'Try asking something like "search for broccoli" to find broccoli recipes.</p>')
    reprompt_text = 'Sorry, I didn\'t catch that. Please ask something like "search for broccoli" to find broccoli recipes.'
    
    should_end_session = False
    
    return build_response(session_attributes, build_speechlet_response(
        speech_output, False, False, reprompt_text, should_end_session))


def alexa_search_for_recipe(intent, session):
    if 'attributes' in session.keys():
        session_attributes = session['attributes']
    else:
        session_attributes = {}
    should_end_session = False
    reprompt_text = 'Sorry, I didn\'t catch that. Please say "recipe" and then the number of the result.'
    session_attributes['new_session'] = False

    # Error handling: User did not provide a search string
    if 'value' not in intent['slots']['RecipeSearchString'].keys():
        speech_output = ('<p>Sorry, it seems that you forgot to say what you want to search for. '
                         'Try saying "search for" and then a recipe or ingredient.</p>')
        return build_response(session_attributes, build_speechlet_response(
            speech_output, False, False, reprompt_text, False))
    
    # Search the Skinnytaste site for the search string provided by the user
    recipe_results = search_for_recipe(intent['slots']['RecipeSearchString']['value'])

    # Loop through the search results and append them to the speech output
    speech_output = '<p>Here are the top search results for "{search_string}": </p>'.format(
        search_string=intent['slots']['RecipeSearchString']['value']
    )

    for search_result_counter in range(0, min([len(recipe_results), 3])):  # We take the min() to account for searches with less than 3 results
        speech_output += "Recipe {result_count}: {result}. ".format(
            result_count=search_result_counter + 1,
            result=recipe_results[search_result_counter]['recipe_title']
            )

    # Save the search results to the session for later
    session_attributes['recipe_results'] = recipe_results

    # Finish the speech output
    speech_output += '<p>Which recipe number would you like? Say "recipe" and then the number of the result.</p>'

    card_title = 'Search results for "{search}":'.format(search=intent['slots']['RecipeSearchString']['value'])
    card_output = BeautifulSoup(speech_output, 'html.parser').get_text()
    
    card_output = card_output.replace('Recipe', '\nRecipe')
    card_output = card_output.replace('Which recipe', '\n\nWhich recipe')

    return build_response(session_attributes, build_speechlet_response(
        speech_output, card_title, card_output, reprompt_text, should_end_session))


def alexa_pick_recipe_number(intent, session):
    session_attributes = session['attributes']
    should_end_session = True
    reprompt_text = "Sorry, I didn't catch that. Please repeat."

    # Error handling: User did not specify a recipe number
    if 'value' not in intent['slots']['RecipeNumber'].keys():
        speech_output = ('<p>Please pick a recipe number from one to three. '
                         'Say "Recipe" and then the number of the recipe."</p>')
        return build_response(session_attributes, build_speechlet_response(
            speech_output, False, False, reprompt_text, False))
    
    recipe_number = int(intent['slots']['RecipeNumber']['value'])

    # Error handling: User specified an invalid recipe number
    if recipe_number > 3 or recipe_number < 1:
        speech_output = ('<p>Please pick a recipe number from one to three. '
                         'Say "Recipe" and then the number of the recipe."</p>')
        return build_response(session_attributes, build_speechlet_response(
            speech_output, False, False, reprompt_text, False))

    # Retrieve the search results from the first interaction,
    # then retrieve the URL for the chosen recipe number
    recipe_results = session_attributes['recipe_results']
    recipe_title = recipe_results[recipe_number - 1]['recipe_title']
    recipe_url = recipe_results[recipe_number - 1]['recipe_url']

    # Scrape the recipe details from Skinnytaste.com
    recipe_details = get_recipe_details(recipe_title, recipe_url)

    # Save recipe details and the current recipe step as a session attribute for later access
    session_attributes['recipe_details'] = recipe_details

    # Save current recipe step to the database
    set_current_recipe_step(session, 1, recipe_details)
    # session_attributes['current_recipe_step'] = 1

    # Because this is the first step, repeat the name of the recipe for the user.
    current_recipe_step = get_current_recipe_step(session)
    if current_recipe_step == 1:
        speech_output = 'Here are the instructions for {recipe_title}. '.format(recipe_title=recipe_title)

    # Create a list of all the instructions, separated by new lines, for the Alexa card
    list_of_instructions = ''
    for step_number, instruction in enumerate(recipe_details['instructions']):
        list_of_instructions += 'Step {step_number}: {instruction}\n'.format(
            step_number=step_number + 1,
            instruction=instruction
        )

    # Add the current recipe step instruction to the speech output
    speech_output += read_recipe_instruction(session)

    # Create the Alexa card with the entire recipe
    card_title = 'Recipe Instructions for {recipe_title}'.format(recipe_title=recipe_title)
    card_output = list_of_instructions

    return build_response(session_attributes, build_speechlet_response(
        speech_output, card_title, card_output, reprompt_text, should_end_session))


def alexa_next_step(intent, session):
    print 'intent:'
    pprint(intent)
    
    print 'session:'
    pprint(session)
    current_recipe_step = get_current_recipe_step(session)
    
    session_attributes = session['attributes']

    should_end_session = True
    reprompt_text = "Sorry, I didn't catch that. Please repeat."

    # Increase the recipe step number
    set_current_recipe_step(session, current_recipe_step + 1, session_attributes['recipe_details'])

    speech_output = read_recipe_instruction(session)

    if current_recipe_step == len(session_attributes['recipe_details']['instructions']):
        speech_output += "<p>This was the last step. If you're done cooking, just say 'End'! Enjoy your meal!</p>"

    return build_response(session_attributes, build_speechlet_response(
        speech_output, False, False, reprompt_text, should_end_session))


def alexa_previous_step(intent, session):
    current_recipe_step = get_current_recipe_step(session)
    
    session_attributes = session['attributes']

    should_end_session = True
    reprompt_text = "Sorry, I didn't catch that. Please repeat."

    # Decrease the recipe step number
    set_current_recipe_step(session, current_recipe_step - 1, session_attributes['recipe_details'])

    speech_output = read_recipe_instruction(session)

    return build_response(session_attributes, build_speechlet_response(
        speech_output, False, False, reprompt_text, should_end_session))


def alexa_repeat_step(intent, session):
    print 'intent:'
    pprint(intent)
    
    print 'session:'
    pprint(session)
    current_recipe_step = get_current_recipe_step(session)
    
    session_attributes = session['attributes']

    should_end_session = True
    reprompt_text = "Sorry, I didn't catch that. Please repeat."

    speech_output = read_recipe_instruction(session)

    return build_response(session_attributes, build_speechlet_response(
        speech_output, False, False, reprompt_text, should_end_session))


def alexa_help(intent, session, invalid_intent=False):
    if 'attributes' in session.keys():
        session_attributes = session['attributes']
    else:
        session_attributes = {}
    should_end_session = False
    reprompt_text = "Sorry, I didn't catch that. Please repeat."

    if invalid_intent:
        speech_output = ('<p>Hmm.. sorry, but that wasn\'t a valid command. '
                         'Try saying something like "search for broccoli" to find broccoli recipes. '
                         'If you\'re in the middle of a recipe, you can say "Next Step", "Previous Step" or "Repeat Step" '
                         'to navigate the recipe instructions.</p>')
    else:
        speech_output = ('<p>Start using the Skinny Taste Alexa skill by searching for a recipe. '
                        'Try something like "search for broccoli" to find broccoli recipes.</p>')

    return build_response(session_attributes, build_speechlet_response(
        speech_output, False, False, reprompt_text, should_end_session))


def alexa_end_session(intent, session):
    if 'attributes' in session.keys():
        session_attributes = session['attributes']
    else:
        session_attributes = {}
    should_end_session = True
    reprompt_text = "Sorry, I didn't catch that. Please repeat."

    speech_output = ('<p>Thanks for using the Skinny Taste Alexa skill! Happy cooking!</p>')

    return build_response(session_attributes, build_speechlet_response(
        speech_output, False, False, reprompt_text, should_end_session))

# --------------- Helpers that build all of the responses ---------------------

def build_speechlet_response(speech_output, card_title, card_output, reprompt_text, should_end_session):
    speechlet_response = {
        'outputSpeech': {
            'type': 'SSML',
            'ssml': '<speak>' + speech_output + '</speak>'
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': reprompt_text
            }
        },
        'shouldEndSession': should_end_session
    }

    if card_title:
        speechlet_response['card'] = {
            'type': 'Standard',
            'title': card_title,
            'text': card_output
        }

    return speechlet_response


def build_response(session_attributes, speechlet_response):
    return {
        'version': '1.0',
        'sessionAttributes': session_attributes,
        'response': speechlet_response
    }


# ----------------------- Search for a recipe -----------------------------

def get_current_recipe_step(session):
    client = boto3.client('dynamodb')
    get_response = client.get_item(
        TableName = "skinnytaste",
        Key = {
            "user_id": {
                "S": session['user']['userId']
            }
        }
    )
    current_recipe_step = int(get_response['Item']['CurrentStep']['N'])

    # When you get the current recipe step from the database, also double-check to see if the current session knows the recipe instructions and ingredients
    # If not, get the instructions and ingredients from the database and add to the current session.
    if 'attributes' not in session.keys():
        session['attributes'] = {}
    
    if 'recipe_details' not in session['attributes'].keys():
        recipe_instructions = []
        recipe_ingredients = []

        for instruction in get_response['Item']['RecipeInstructions']['L']:
            recipe_instructions.append(instruction['S'])

        for ingredient in get_response['Item']['RecipeIngredients']['L']:
            recipe_ingredients.append(ingredient['S'])

        session['attributes']['recipe_details'] = {
            'instructions': [], 
            'ingredients': []
        }

        session['attributes']['recipe_details']['instructions'] = recipe_instructions
        session['attributes']['recipe_details']['ingredients'] = recipe_ingredients

    return current_recipe_step


def set_current_recipe_step(session, recipe_step, recipe_details):
    client = boto3.client('dynamodb')
    recipe_instructions_db = []
    recipe_ingredients_db = []

    for instruction in recipe_details['instructions']:
        recipe_instructions_db.append({
            "S": instruction
        })

    for ingredient in recipe_details['ingredients']:
        recipe_ingredients_db.append({
            "S": ingredient
        })

    item = {
        "user_id": {
            "S": session['user']['userId']
        },
        "CurrentStep": {
            "N": str(recipe_step)
        },
        "RecipeInstructions": {
            "L": recipe_instructions_db
        },
        "RecipeIngredients": {
            "L": recipe_ingredients_db
        }
    }
    client.put_item(TableName="skinnytaste", Item=item)


def read_recipe_instruction(session):
    current_recipe_step = get_current_recipe_step(session)
    current_recipe_instruction = session['attributes']['recipe_details']['instructions'][current_recipe_step - 1]
    total_number_of_steps = len(session['attributes']['recipe_details']['instructions'])

    current_recipe_step_speech_output = '<p>Step {step_number} of {total_steps}: {instruction} </p>'.format(
        step_number=current_recipe_step,
        total_steps=total_number_of_steps,
        instruction=current_recipe_instruction.replace(' . ', '')
    )

    if current_recipe_step != total_number_of_steps:
        current_recipe_step_speech_output += '<p>Say "Alexa, Ask Skinnytaste What\'s the next step?" to continue.</p>'
    else:
        current_recipe_step_speech_output += '<p>This was the final step! Happy cooking!</p>'

    return current_recipe_step_speech_output


def search_for_recipe(search_query):
    # Create a list of search results
    recipe_results = []

    # Scrape the search results page
    search_results_page = requests.get('http://www.skinnytaste.com/?s={search_query}'.format(
        search_query=urllib.quote_plus(search_query))
    )
    soup = BeautifulSoup(search_results_page.text, 'html.parser')
    
    # Filter the search results page by the actual results
    search_results = soup.find_all('a', {'rel': 'bookmark'})
    for item in search_results:
        if item.h2:
            recipe_results.append({
                'recipe_title': item.h2.text,
                'recipe_url': item['href']
            })    

    return recipe_results

# ----------------------- Get the details of a recipe -----------------------------

def get_recipe_details(recipe_title, recipe_url):
    # Create the recipe details dictionary
    recipe_details = {
        'ingredients': [],
        'instructions': []
    }

    # Scrape the recipe page
    recipe_page = requests.get(recipe_url)
    soup = BeautifulSoup(recipe_page.text, 'html.parser')

    # Scrape ingredients from the recipe page, add to recipe details
    ingredients_elements = soup.find_all(class_='ingredient')
    # Check to see if the recipe was created after the site redesign, where ingredients and instructions are clearly labeled
    # If not, we'll have to scrape the page a different way
    if ingredients_elements:
        for ingredient_item in ingredients_elements:
            recipe_details['ingredients'].append(ingredient_item.text)

        # Scrape instructions from the recipe page, add to recipe details
        instructions_elements = soup.find(class_='instructions').find_all('li')
        for instructions_item in instructions_elements:
            # This bit removes any links that sometimes show up in the instructions.
            if instructions_item.a:
                recipe_details['instructions'].append(
                    instructions_item.text.replace(instructions_item.a.text, '')
                )
            else:
                recipe_details['instructions'].append(instructions_item.text)
    else:
        # The recipe is an older recipe and ingredients and instructions aren't properly labeled, so we'll have to scrape a different way
        content = soup.find_all('div', class_='post')

        # Capture the ingredients
        ingredients_elements = content[0].find_all('li')
        for ingredient_item in ingredients_elements:
            recipe_details['ingredients'].append(ingredient_item.text)

        # Capture the instructions
        instructions_capture_flag = False
        instructions_elements = content[0].find_all('p')
        for instructions_item in instructions_elements:
            if 'Get new free recipes and exclusive content delivered right to your inbox:' in instructions_item.text:
                instructions_capture_flag = False

            if instructions_capture_flag:
                # This bit removes any links that sometimes show up in the instructions.
                if instructions_item.a:
                    recipe_details['instructions'].append(
                        instructions_item.text.replace(instructions_item.a.text, '')
                    )
                else:
                    recipe_details['instructions'].append(instructions_item.text)

            if 'Directions:' in instructions_item.text:
                instructions_capture_flag = True

    return recipe_details


if __name__ == "__main__":
    recipe_results = search_for_recipe('chicken sausage and peppers macaroni casserole')
    recipe_details = get_recipe_details(recipe_results[0]['recipe_title'], recipe_results[0]['recipe_url'])
    pprint(recipe_details)