class LimitExceededError(Exception):
    """Exception raised when a limit or threshold has been exceeded."""


class WebParseError(Exception):
    """Exception raised when webpage parsing returns no usable content."""


class TranscriptDownloadError(Exception):
    """Exception raised when yt-dlp transiently fails to fetch subtitles."""


class FetchTranscriptError(Exception):
    """Exception raised when transcript retrieval fails via all backends."""


class ReplicateError(Exception):
    """Exception raised when the Replicate API answers with an HTTP 4xx/5xx."""

    def __init__(self, status: int, message: str) -> None:
        """Keep the HTTP status so the caller can tell a transient error apart."""
        self.status = status
        super().__init__(message)


class TranscriptionError(Exception):
    """Exception raised when a transcription fails or returns invalid output."""
