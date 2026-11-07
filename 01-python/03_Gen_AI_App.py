# pip install boto3 
import os
import boto3
from dotenv import load_dotenv

# Load .env file content into the program
load_dotenv()

message = input("Enter your prompt: ")


client = boto3.client("bedrock-runtime")


response = client.converse(
    modelId="mistral.mistral-7b-instruct-v0:2",
    messages=[
        {
            "role": "user",
            "content": [{"text": message}], 
        }
    ],
    inferenceConfig={"temperature": 0.7, "maxTokens": 100},
)

# Extract and print just the text response from the model
output_text = response["output"]["message"]["content"][0]["text"]
print("\nResponse:")
print(output_text)



# Frameworks langchain langgraph mf antropic claudeagentsdk [vendors]