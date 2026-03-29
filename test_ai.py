import requests
import os

token = os.environ.get('AWS_BEARER_TOKEN_BEDROCK', '')
print("Token found:", "YES" if token else "NO")

models = [
    'anthropic.claude-haiku-4-5-20251001-v1:0',
    'anthropic.claude-3-haiku-20240307-v1:0',
    'anthropic.claude-3-5-haiku-20241022-v1:0',
]

for model in models:
    url = f'https://bedrock-runtime.us-east-1.amazonaws.com/model/{model}/invoke'
    r = requests.post(url,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        },
        json={
            'anthropic_version': 'bedrock-2023-05-31',
            'max_tokens': 20,
            'messages': [{'role': 'user', 'content': 'Say hi'}]
        }
    )
    print(f'{model}: {r.status_code}')
    if r.status_code == 200:
        print('WORKING! Response:', r.json()['content'][0]['text'])
        break
    else:
        print('Error:', r.text[:100])