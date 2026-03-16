class BaseTTS:
    def __init__(self, language: str = "no"):
        self.language = language

    def speak(self, text: str):
        raise NotImplementedError("Subclasses must implement speak() method")
