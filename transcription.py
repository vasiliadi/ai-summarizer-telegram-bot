import time

from config import replicate_client


def transcribe(file, sleep_time=10):
    model = replicate_client.models.get("vaibhavs10/incredibly-fast-whisper")
    version = model.versions.get(model.versions.list()[0].id)
    with open(file, "rb") as audio:
        prediction = replicate_client.predictions.create(
            version=version, input={"audio": audio}
        )
    while prediction.status != "succeeded":
        if prediction.status == "failed" or prediction.status == "canceled":
            raise Exception("File can't be transcribed.")
        prediction.reload()
        time.sleep(sleep_time)
    return prediction.output["text"]
