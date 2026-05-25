class LimitExceededError(Exception):
    """Exception raised when a limit or threshold has been exceeded."""


class WebParseError(Exception):
    """Exception raised when webpage parsing returns no usable content."""


class TranscriptDownloadError(Exception):
    """Exception raised when yt-dlp transiently fails to fetch subtitles."""
