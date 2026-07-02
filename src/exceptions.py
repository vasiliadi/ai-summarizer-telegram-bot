class LimitExceededError(Exception):
    """Exception raised when a limit or threshold has been exceeded."""


class WebParseError(Exception):
    """Exception raised when webpage parsing returns no usable content."""


class TranscriptDownloadError(Exception):
    """Exception raised when yt-dlp transiently fails to fetch subtitles."""


class FetchTranscriptError(Exception):
    """Exception raised when transcript retrieval fails via all backends."""


class GeminiIncompleteResponseError(Exception):
    """Exception raised when Gemini returns empty output or incomplete file metadata."""
