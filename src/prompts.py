# ruff: noqa: E501

# Prompts
PROMPTS = {
    "basic_prompt_for_transcript": "Read or listen carefully transcription or audio file and provide a detailed summary:",
    "soap_prompt_for_transcript": """
        I need you to analyze and summarize a transcript or audio file using the SOAP method.
        Please note that this transcript may contain speech recognition errors, inconsistent punctuation, non-verbal markers [music], [laughing], etc., and informal spoken language.

        Notes on handling transcript issues:

        Clean up obvious speech recognition errors when meaning is clear from context
        Ignore non-verbal markers unless relevant to content meaning
        If a section is unclear due to transcript quality, note "Potential transcript gap" and continue with next clear segment
        Convert casual spoken language into professional writing while maintaining original meaning

        Present all information in clear, professional language, organizing complex ideas into digestible segments while preserving important details and relationships.

        Please analyze and summarize the content following this structure:

        Title: [Inferred title based on the content]

        Introduction: [1-2 sentences introducing the main topic]

        Subjective (S)
        Presenter's stated opinions and beliefs
        Personal experiences shared
        Emotional responses or reactions described
        Attitudes expressed towards the topic
        Hypothetical scenarios presented
        Arguments based on personal perspective
        User/customer testimonials mentioned
        Perceived challenges or opportunities discussed

        Objective (O)
        Factual information presented (5-10 key points)
        Verifiable data and statistics
        Research findings or studies cited
        Historical events referenced
        Technical specifications or processes explained
        Industry standards mentioned
        Market data or trends presented
        Expert quotes or citations (cleaned up from transcript errors)
        Measurable outcomes discussed

        Assessment (A)
        Analyze the relationship between subjective and objective elements:
        How does the presenter use data to support their opinions?
        What connections are made between personal experience and factual evidence?
        Which arguments are supported by strong evidence vs. personal belief?
        What patterns emerge from combining subjective and objective information?
        How do examples and case studies reinforce the main points?
        What gaps exist between opinions and available data?
        How do different perspectives contribute to the overall message?

        Plan (P)
        Organize the information into a coherent narrative:
        Main conclusion or key takeaway
        Primary supporting arguments (minimum 5)
        Practical applications or recommendations
        Next steps or action items suggested
        Resources or tools recommended
        Future implications discussed
        Call-to-action or key learnings emphasized

        Here is transcript or audio file:
        """,
    "key_points_for_transcript": """
        You are tasked with summarizing a YouTube video transcript into at least 5 key points.

        This task comes with several challenges:
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
        b. Identify the main topics or themes discussed in the video.
        c. Look for key information, important facts, or central ideas presented.

        3. Summarization:
        a. Distill the content into at least 5 key points.
        b. Ensure each key point captures a distinct and significant aspect of the video's content.
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

        Remember to focus on the most important and relevant information from the video.
        Your summary should provide a clear and accurate representation of the video's content, despite any challenges in the original transcript.

        Here is transcript or audio file:
        """,
}

# System Instructions
TRANSLATION_SYSTEM_INSTRUCTION = """
    You are a language model specializing in accurate, context-sensitive translations.
    Translate each text with precise meaning and maintain the original tone and style.
    Adapt idioms, cultural references, and metaphors for naturalness in the target language,
    while providing brief explanations directly in the text, if necessary.
    Avoid literal translations unless they are essential.
    When terms have multiple meanings, use the context to select the best fit.
    Do not translate proper nouns or technical terms unless widely recognized equivalents exist.
    Ensure consistent terminology, especially for technical or specialized language.
    Use polite, respectful language, adjusting formality as appropriate for the text type (e.g., legal, business, casual).
    I want you to only reply the translation, do not write notes or explanations.
"""
