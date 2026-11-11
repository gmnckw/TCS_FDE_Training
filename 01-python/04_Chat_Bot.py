# pip install boto3 

import os 
import dotenv 
import boto3
from dotenv import load_dotenv 

# .env file  content into the program
load_dotenv()

client = boto3.client('bedrock-runtime')

while True:
    user_input = input("prompt: ").strip().lower()

    if user_input == "exit":
        print("thank you")
        break
    else: 
        response = client.converse(
            modelId= "mistral.mistral-7b-instruct-v0:2",
            messages=[
                {
                    "role": "user",
                    "content": [{"text": user_input}]
                }
            ],
            inferenceConfig={"temperature": 0.7, "maxTokens": 100}    
        )

        print(response["output"]["message"]["content"][0]["text"])


# Frameworks langchain langgraph mf antropic claudeagentsdk [vendors]