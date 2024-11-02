BASIC_PROMPT_FOR_TRANSCRIPT = (
    "Read carefully transcription and provide a detailed summary:"
)

SOAP_PROMPT_FOR_TRANSCRIPT = """
    I need you to analyze and summarize a YouTube video transcript using the SOAP method.
    Please note that this transcript may contain speech recognition errors, inconsistent punctuation, non-verbal markers [music], [laughing], etc., and informal spoken language.
    Please analyze and summarize the content following this structure:

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

    Notes on handling transcript issues:

    Clean up obvious speech recognition errors when meaning is clear from context
    Ignore non-verbal markers unless relevant to content meaning
    If a section is unclear due to transcript quality, note "Potential transcript gap" and continue with next clear segment
    Convert casual spoken language into professional writing while maintaining original meaning

    Present all information in clear, professional language, organizing complex ideas into digestible segments while preserving important details and relationships.

    Here is transcript:
"""  # noqa: E501

ACTION_POINTS_FOR_TRANSCRIPT = """
    You will be summarizing a YouTube video transcript into action points.

    This task requires careful attention as the transcript may contain several challenges:
    1. Speech recognition errors
    2. Inconsistent punctuation
    3. Non-verbal markers (e.g., [music], [laughing])
    4. Informal spoken language

    To effectively summarize the transcript into action points, follow these steps:

    1. Read through the entire transcript to get a general understanding of the content.
    2. Ignore non-verbal markers and focus on the actual speech content.
    3. As you read, identify the main topics or themes discussed in the video.
    4. Look for specific actions, tips, or advice mentioned by the speaker(s).
    5. Pay attention to repeated ideas or concepts, as these are likely to be important.
    6. Disregard filler words, false starts, and other speech disfluencies common in spoken language.
    7. If you encounter potential speech recognition errors, use context to infer the intended meaning.
    8. Consolidate similar ideas into single, concise action points.
    9. Phrase each action point as a clear, actionable statement.
    10. Aim for 5-10 action points, depending on the length and complexity of the transcript.

    Format your summary as a list of action points, each starting with a verb. For example:

    1. Implement daily meditation practice to reduce stress.
    2. Create a weekly meal plan to improve nutrition.
    3. Set specific, measurable goals for personal development.

    Your final output should be formatted as follows, please ignore xml tags in output:

    <action_points>
    1. [First action point]
    2. [Second action point]
    3. [Third action point]
    ...
    </action_points>

    Please provide your summarized action points based on the given transcript.

    Here is transcript:
"""  # noqa: E501

BASIC_PROMPT_FOR_WEBPAGE = (
    "Read carefully webpage content and provide a detailed summary:"
)

BASIC_PROMPT_FOR_FILE = (
    "Listen carefully to the following audio file. Provide a detailed summary."
)
