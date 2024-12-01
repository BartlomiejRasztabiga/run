from abc import ABC, abstractmethod

from dotenv import load_dotenv
from openai import OpenAI

from prompts import SYSTEM_PROMPT

load_dotenv()

client = OpenAI()


def get_model(model_name):
    if model_name == "gpt-4o-mini":
        return OpenAIModel(model_name)
    if model_name == "gpt-4o":
        return OpenAIModel(model_name)
    else:
        return None


class Model(ABC):
    def ask_model(self, use_case, user_prompt):
        prompt = f"Use case: {use_case}\n\n{user_prompt}"
        return self.ask_model_internal(prompt)

    @abstractmethod
    def ask_model_internal(self, prompt):
        pass


class OpenAIModel(Model):
    def __init__(self, model):
        self.model = model

    def ask_model_internal(self, prompt):
        completion = client.chat.completions.create(model=self.model, messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ])
        return completion.choices[0].message.content
