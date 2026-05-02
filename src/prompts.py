# ruff: noqa: E501

# Prompts
PROMPTS = {
    "basic_prompt_for_transcript": """
        Read or listen carefully to the provided content below and provide a detailed summary.

        STRICTLY FORBIDDEN: Do not preface the response with any introductory phrases like "Here is the summary", "Here are the key points", etc. Start directly with the content.

        Here is the provided content:
        """,
    "key_points_for_transcript": """
        You are tasked with summarizing the provided content below into at least 5 key points.

        This task comes with several challenges (if the provided content is a transcript):
        1. The transcript may contain errors, such as incorrect word recognition or lack of punctuation.
        2. It's more akin to video subtitles than a formal transcript.
        3. The transcript may include non-verbal cues like [music] or [laughing].

        To complete this task effectively, follow these steps:

        1. Preprocessing:
        a. Remove non-verbal cues (e.g., [music], [laughing]) from the transcript.
        b. Attempt to add basic punctuation where it seems appropriate.
        c. Correct obvious word recognition errors based on context.

        2. Content Analysis:
        a. Read through the preprocessed transcript carefully.
        b. Identify the main topics or themes discussed in the content.
        c. Look for key information, important facts, or central ideas presented.

        3. Summarization:
        a. Distill the content into at least 5 key points.
        b. Ensure each key point captures a distinct and significant aspect of the content.
        c. Present the information in a clear, concise manner.
        d. If the video content allows for more than 5 key points, include them as well.

        4. Output Formatting:
        Present your summary in the following format:

        - [Concise statement of the first main idea]
        - [Concise statement of the second main idea]
        - [Concise statement of the third main idea]
        - [Concise statement of the fourth main idea]
        - [Concise statement of the fifth main idea]
        [Additional key points if applicable]

        Remember to focus on the most important and relevant information from the content.
        Your summary should provide a clear and accurate representation of the content, despite any challenges in the original transcript.
        Do not include preprocessing information.
        STRICTLY FORBIDDEN: Do not preface the response with any introductory phrases like "Here is the summary", "Here are the key points", etc. Start directly with the content.

        Here is the provided content:
        """,
}

SYSTEM_INSTRUCTION = """
    You are a helpful assistant.
    Your goal is to provide a summary of the content provided by the user.
    You must reply in {language} language.
"""
