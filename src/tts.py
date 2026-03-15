class BaseTTS:
    def speak(self, text: str):
        raise NotImplementedError("Subclasses must implement speak() method")
