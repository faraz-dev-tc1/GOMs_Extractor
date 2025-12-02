"""
Token usage tracker for Gemini API calls.
"""

from dataclasses import dataclass
import logging

@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    response_tokens: int = 0
    total_tokens: int = 0

class TokenTracker:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TokenTracker, cls).__new__(cls)
            cls._instance.reset()
        return cls._instance

    def reset(self):
        self.total_usage = TokenUsage()
        self.request_log = []

    def track_request(self, source: str, response):
        """
        Tracks token usage from a Gemini response object.
        Args:
            source: The name of the component/function making the call.
            response: The GenerateContentResponse object from Vertex AI.
        """
        try:
            # Check if usage_metadata exists (it might be missing in some error cases or mocked responses)
            if not hasattr(response, 'usage_metadata') or not response.usage_metadata:
                print(f"DEBUG: No usage metadata in response from {source}")
                return

            usage = response.usage_metadata
            prompt_tokens = usage.prompt_token_count
            response_tokens = usage.candidates_token_count
            total_tokens = usage.total_token_count

            self.total_usage.prompt_tokens += prompt_tokens
            self.total_usage.response_tokens += response_tokens
            self.total_usage.total_tokens += total_tokens

            log_entry = {
                "source": source,
                "prompt_tokens": prompt_tokens,
                "response_tokens": response_tokens,
                "total_tokens": total_tokens
            }
            self.request_log.append(log_entry)
            
            print(f"TOKEN USAGE [{source}]: Prompt: {prompt_tokens}, Response: {response_tokens}, Total: {total_tokens}")
        except Exception as e:
            print(f"WARNING: Failed to track token usage: {e}")

    def get_summary(self):
        return f"Total Token Usage - Prompt: {self.total_usage.prompt_tokens}, Response: {self.total_usage.response_tokens}, Total: {self.total_usage.total_tokens}"

    def print_summary(self):
        print("\n" + "="*50)
        print("TOKEN USAGE SUMMARY")
        print("="*50)
        print(f"{'Source':<30} | {'Prompt':<6} | {'Resp':<6} | {'Total':<6}")
        print("-" * 50)
        for entry in self.request_log:
            print(f"{entry['source']:<30} | {entry['prompt_tokens']:<6} | {entry['response_tokens']:<6} | {entry['total_tokens']:<6}")
        print("-" * 50)
        print(self.get_summary())
        print("="*50 + "\n")
