import boto3
import json
import logging
import os
import math

from base64 import b64decode
from urllib.parse import parse_qs
from functools import lru_cache
from random import randint
from urllib.parse import urlparse

import urllib

auth_token = 'YOUR SLACK BOT TOKEN HERE'
ENCRYPTED_EXPECTED_TOKEN = os.environ['kmsEncryptedToken']

SLACK_URL = "https://slack.com/api/chat.postMessage"
SLACK_MODAL = "https://slack.com/api/views.open"
SLACK_EPHEMERAL ="https://slack.com/api/chat.postEphemeral"

client = boto3.client('sns')
kms = boto3.client('kms')
s3 = boto3.resource('s3')

expected_token = kms.decrypt(
    CiphertextBlob=b64decode(ENCRYPTED_EXPECTED_TOKEN),
    EncryptionContext={'LambdaFunctionName': os.environ['AWS_LAMBDA_FUNCTION_NAME']}
)['Plaintext'].decode('utf-8')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

subcommand_list = ['quote',
                'echo',
                'powerball',
                'prime',
                'submittals','submittal',
                'rfis','rfi',
                'due',
                'add',
                'list',
                'admindelete'
]


def lambda_handler(event, context):
    #print(event)
    body_event =  event['body']
    #print("body_event = " + body_event)
    params = parse_qs(event['body'])
    #print("params = ")
    print( params)
    
    #variables used for the 'add project' modal
    number_input = None
    name_input = None
    link_input = None
    channel_input = None
    
    #payload is only in params if it is a view submission (I think?)
    if 'payload' in params.keys():
        payload_event = params['payload'][0]
        payload_event = json.loads(payload_event)
        print(payload_event)
        
        if payload_event['view']['callback_id'] =='optimus_confirmation':
            print("OPTIMUS CONFIRMATION")
            return optimus_confirmation(payload_event)
            
        elif payload_event['view']['callback_id'] =='optimus_add':  
            print("OPTIMUS ADD")
            return optimus_add(payload_event)
        
        elif payload_event['view']['callback_id'] =='optimus_admindelete' and payload_event['type']=='view_submission':   
            print("OPTIMUS ADMIN")
            return optimus_admindelete(payload_event)    
        
        
        #else:
        #TODO: ADD ERROR MESSAGE IF SOMEHOW THE MODAL IS NOT RECOGNIZED    
        
    # else:
    #     print('not a modal')
    #     token = None    
    
    # if token is None:
    token = params['token'][0]
    
    if token != expected_token:
        logger.error("Request token (%s) does not match expected", token)
        return respond(Exception('Invalid request token'))

    user = params['user_id'][0]
    command = params['command'][0]
    channel = params['channel_name'][0]
    channel_id = params['channel_id'][0]
    trigger_id = params['trigger_id'][0]
    
    optimus_join_channel(channel)
    
    
    if 'text' not in params:
        response = 'For a list of available commands, type \"/optimus help\".'
        subcommand=None
        subsubcommand=None
        
    else:
        command_text = params['text'][0].split(" ")
        subcommand = command_text[0].lower()
        if subcommand == 'help':
            response =('Here are the commands I can process:\r\n'
                        '\t • */optimus help*, the command you just used.\r\n'
                        '\t • */optimus prime [number]*, if you want to know if [number] is prime or not.\r\n'
                        '\t • */optimus quote*, if you want me to share some of my wisdom with you.\r\n'
                        '\t • */optimus submittals [project number]* will have me fetch all the currently open submittals for your project.\r\n'
                        '\t • */optimus RFIs [project number]* will have me fetch all the currently open RFIs for your project.\r\n'
                        '\t • */optimus due [project number]* will return all the submittals and RFIs that are either due today or overdue.\r\n'
                        '\t • */optimus add* will allow you to add or update a project for me to monitor.\r\n'
                        '\t • */optimus list* will display all the projects I currently monitor.\r\n'
            )
            subcommand = None
            subsubcommand = None
            return sendhttp200('ephemeral',response)
            
        elif subcommand not in subcommand_list:
            response = 'I do not recognize that command. Type \"/optimus help\" for a list of all recognized commands.'
            subcommand = None
            subsubcommand = None
            return sendhttp200('ephemeral',response)
            
        else:
            if len(command_text) > 1:
                subsubcommand = command_text[1].lower()
            else:
                subsubcommand = None
                
            if subcommand =='add':
                #create modal menu
                modal_view_json = open('modal_block_kit.json', )
                modal_view = json.load(modal_view_json)
                
                #update name on modal
                modal_view['blocks'][0]['text']['text']=modal_view['blocks'][0]['text']['text'].replace('David',f'<@{user}>')
                modal_view['private_metadata'] = channel_id

                payload = {
                    "trigger_id": trigger_id,
                    "view": modal_view
                }
                
                post_to_slack(payload,SLACK_MODAL)
                return {'statusCode': '200'}
                
            if subcommand =='list':
                #create modal menu
                modal_view_json = open('project_list_modal.json', )
                modal_view = json.load(modal_view_json)
                
                update_list_modal(modal_view)

                payload = {
                    "trigger_id": trigger_id,
                    "view": modal_view
                }
                
                post_to_slack(payload,SLACK_MODAL)
                return {'statusCode': '200'}
                
            if subcommand =='admindelete':
                #create modal menu
                modal_view_json = open('admindelete_project_modal.json', )
                modal_view = json.load(modal_view_json)
                
                admindelete_modal(modal_view)
                #print(modal_view)

                payload = {
                    "trigger_id": trigger_id,
                    "view": modal_view
                }
                
                #print('READY TO BE SENT')
                #print(payload)
                
                post_to_slack(payload,SLACK_MODAL)
                return {'statusCode': '200'}

     
            elif subcommand is not None:
                
                # publish SNS message to delegate the actual work to worker lambda function
                message = {
                    "subcommand": subcommand,
                    "subsubcommand": subsubcommand,
                    "channel_id": channel_id,
                    "trigger_id": trigger_id
                }
                
                
                print(json.dumps(message))
                
                response_sns = client.publish(
                    TargetArn='YOUR SNS ARN',
                    Message=json.dumps({'default': json.dumps(message)}),
                    MessageStructure='json'
                )
                
                return sendhttp200('in_channel',None)

    
    
def post_to_slack(json_payload,post_url):

    #encode content
    payload = json.dumps(json_payload).encode('utf8')
    
    request = urllib.request.Request(post_url, data=payload, method="POST")
    request.add_header( 'Content-Type', 'application/json;charset=utf-8' )
    request.add_header( 'Authorization', 'Bearer ' + auth_token )

    # Fire off the request!
    x = urllib.request.urlopen(request).read()
    print(x)
    
    
def sendhttp200(response_type,response):
    
    jsonpayload = {
        "response_type": response_type,
        "text": response
    }
    
    return {
        'statusCode': '200',
        'body': json.dumps(jsonpayload).encode('utf8'),
        'headers': {
            'Content-Type': 'application/json',
        },
    }
    
    
    
def send_confirmation_modal(project, combined_input): 
    
    modal_view_json = open('project_add_existing.json', )
    modal_view = json.load(modal_view_json)
    
    project_number = project['Project Number']
    project_name = project['Project Name']
    project_link = project['Google Sheets']
    project_channel = project['Slack Channel Id']
    
                
    #update values on modal
    modal_view['blocks'][0]['text']['text']=modal_view['blocks'][0]['text']['text'].replace('project_number',project_number)
    modal_view['blocks'][1]['text']['text'] = (f'*Project Number:* {project_number} \r\n'
                                             f'*Project Name:* {project_name} \r\n'
                                             f'*Project Spreadsheet:* <{project_link}|Google Sheets> \r\n'
                                             f'*Project Channel:* #{get_channel_name(project_channel)}'
                                             )
    
    modal_view['private_metadata'] = json.dumps(combined_input)
    #print(modal_view)
    
    jsonpayload = {
        "response_action": "push",
        "view": modal_view
    }
                
    return {
        'statusCode': '200',
        'body': json.dumps(jsonpayload).encode('utf8'),
        'headers': {
            'Content-Type': 'application/json',
        },
    }
    
    
    
def close_all_modals():
    jsonpayload = {
        "response_action": "clear"
    }
            
    return {
        'statusCode': '200',
        'body': json.dumps(jsonpayload).encode('utf8'),
        'headers': {
            'Content-Type': 'application/json',
        },
    }
    
    
    
def send_warning():
    jsonpayload = {
        "response_action": "errors",
        "errors": {
        "url_block": "This is not a valid Google Sheets URL"
        }
    }
            
    return {
        'statusCode': '200',
        'body': json.dumps(jsonpayload).encode('utf8'),
        'headers': {
            'Content-Type': 'application/json',
        },
    }
    
    
    
def get_channel_name(channel_id):
    #print(channel_id) 
    if channel_id is None:
        return "No channel"
    else:
        querystring = f'https://slack.com/api/conversations.info?channel={channel_id}&pretty=1'
        header = {'Authorization': 'Bearer ' + auth_token}
        req = urllib.request.Request(querystring, headers=header)
        response = urllib.request.urlopen(req).read().decode('utf8')
        channel_json = json.loads(response)
        
        #print(channel_json)
        if channel_json['ok'] == True:
            return channel_json['channel']['name']
        else:
            return channel_id
    
    
def optimus_confirmation(payload_event):
    metadata_dict = json.loads(payload_event['view']['private_metadata'])
            
    #get the monitored project list from s3
    bucket =  'YOUR BUCKET'
    key = 'YOUR BUCKET KEY'

    s3object = s3.Object(bucket, key)
    data = s3object.get()['Body'].read().decode('utf-8')
    json_data = json.loads(data)
    
    #check the array of projects monitored and see if the job is already there
    for project in json_data:
        if project['Project Number'] == metadata_dict['Number Input']:
            project['Project Name'] = metadata_dict['Name Input']
            project['Google Sheets'] = metadata_dict['Link Input']
            project['Slack Channel Id'] = metadata_dict['Channel Input']
            break
            
    json_payload = {
        "channel": metadata_dict['Posted Channel'],
        "user": payload_event['user']['id'],
        "text": 'The project has successfully been updated.'
    }
            
    try:
        s3object.put(Body=(bytes(json.dumps(json_data).encode('UTF-8'))))
        post_to_slack(json_payload,SLACK_EPHEMERAL)
        optimus_join_channel(metadata_dict['Channel Input'])
        return close_all_modals()
    except ClientError as e:
        print("Error uploading to S3")
    
def optimus_add(payload_event):
    modal_input = payload_event['view']['state']['values']
    
    for key in modal_input:
        if 'number_input' in modal_input[key]:
            number_input = modal_input[key]['number_input']['value']
        if 'name_input' in modal_input[key]:
            name_input = modal_input[key]['name_input']['value']
        if 'link_input' in modal_input[key]:
            link_input = modal_input[key]['link_input']['value']
        if 'channel_select' in modal_input[key]:
            channel_input = modal_input[key]['channel_select']['selected_conversation']
            
    combined_input = {'Number Input': number_input,
                        'Name Input': name_input,
                        'Link Input': link_input,
                        'Channel Input': channel_input,
                        'Posted Channel': payload_event['view']['private_metadata']
    }
            
    parsed_link = urlparse(link_input)
    if not parsed_link.scheme and parsed_link is not None:
        link_input = 'https://' + link_input
    
    if parsed_link.netloc != 'docs.google.com':
        return send_warning()
            
    #get the monitored project list from s3
    bucket =  'YOUR BUCKET'
    key = 'YOUR KEY'

    s3object = s3.Object(bucket, key)
    data = s3object.get()['Body'].read().decode('utf-8')
    json_data = json.loads(data)
    
    #check the array of projects monitored and see if the job is already there
    for project in json_data:
        if project['Project Number'] == number_input:
            print('This project is already monitored. Do you want to overwrite the config with the new data?')
            return send_confirmation_modal(project,combined_input)
            break
    else:
        
        bucket_new_entry={
            "Project Number":number_input,
            "Project Name":name_input,
            "Google Sheets":link_input,
            "Slack Channel Id":channel_input
        }
        json_data.append(bucket_new_entry)
        
        
        json_payload = {
            "channel": payload_event['view']['private_metadata'],
            "user": payload_event['user']['id'],
            "text": 'The project has successfully been added to my project list.'
        }
        
        try:
            s3object.put(Body=(bytes(json.dumps(json_data).encode('UTF-8'))))
            post_to_slack(json_payload,SLACK_EPHEMERAL)
            optimus_join_channel(channel_input)
        except ClientError as e:
            print("Error uploading to S3")
            
        return {'statusCode': '200'}
        
def optimus_admindelete(payload_event):
    
    #get the monitored project list from s3
    bucket =  'YOUR BUCKET'
    key = 'YOUR KEY'

    s3object = s3.Object(bucket, key)
    data = s3object.get()['Body'].read().decode('utf-8')
    json_data = json.loads(data)
    
    selected_items = payload_event['view']['state']['values']['checkbox_block']['checkbox_id']['selected_options']
    for item in selected_items:
        for s3item in json_data:
            if s3item['Project Number'] == item['value']:
                json_data.remove(s3item)
    
    try:
        s3object.put(Body=(bytes(json.dumps(json_data).encode('UTF-8'))))
    except ClientError as e:
        print("Error uploading to S3")
    
    return {'statusCode': '200'}
        
def update_list_modal(modal_view):
    
    #get the monitored project list from s3
    bucket =  'YOUR BUCKET'
    key = 'YOUR KEY'

    s3object = s3.Object(bucket, key)
    data = s3object.get()['Body'].read().decode('utf-8')
    json_data = json.loads(data)
    
    divider = {
		"type": "divider"
	}
    
    for project in json_data:
        
        project_number = project['Project Number']
        project_name = project['Project Name']
        project_link = project['Google Sheets']
        project_channel = project['Slack Channel Id']

        project_text = (f'*Project Number:* {project_number} \r\n'
                         f'*Project Name:* {project_name} \r\n'
                         f'*Project Spreadsheet:* <{project_link}|Google Sheets> \r\n'
                         f'*Project Channel:* #{get_channel_name(project_channel)}'
                         )
        
        
        modal_view['blocks'].append(divider)
        modal_view['blocks'].append({"type": "section",
                            		"text": {
                            			"type": "mrkdwn",
                            			"text": project_text
                            		}
                            	}
	    )
	    
def admindelete_modal(modal_view):
    #get the monitored project list from s3
    bucket =  'YOUR BUCKET'
    key = 'YOUR KEY'

    s3object = s3.Object(bucket, key)
    data = s3object.get()['Body'].read().decode('utf-8')
    json_data = json.loads(data)
    
    for project in json_data:
        project_number = project['Project Number']
        project_name = project['Project Name']
        project_link = project['Google Sheets']
        project_channel = project['Slack Channel Id']


            
        modal_view['blocks'][0]['elements'][0]['options'].append(
            {
                "text": {
        		    "type": "mrkdwn",
        		    "text": project_number+" / "+project_name
        		},
        		"value": project_number
        	}
	    )
	    
def optimus_join_channel(channel_id):
    print(f'optimus is joining channel {channel_id}')
    SLACK_JOIN = 'https://slack.com/api/conversations.join'
    
    json_payload = {
            "channel": channel_id,
    }
    post_to_slack(json_payload,SLACK_JOIN)
    
    