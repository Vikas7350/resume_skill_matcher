from openai import OpenAI

client = OpenAI(api_key="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")

response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "user", "content": prompt}
    ]
)
answer = response.choices[0].message.content.strip()
