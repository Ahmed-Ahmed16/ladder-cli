from collections import deque


class Capped:
    def __init__(self, out):
        self.out = out
        self.partial = ""
        self.tail = deque(maxlen=30)
        self.total = 0
        self.finished = False

    def write(self, text):
        if self.finished:
            return self.out.write(text)
        lines = (self.partial + text).split("\n")
        self.partial = lines.pop()
        for line in lines:
            self._line(line + "\n")
        return len(text)

    def _line(self, line):
        self.total += 1
        if self.total <= 10:
            self.out.write(line)
        else:
            self.tail.append(line)

    def flush(self):
        self.out.flush()

    def finish(self, log_path):
        if self.finished:
            return
        if self.partial:
            self._line(self.partial + "\n")
            self.partial = ""
        if self.total > 40:
            print(f"showing 40 of {self.total} lines ({self.total - 40} cut); full log: {log_path}; "
                  f"read more: ladder log {log_path} --grep RE",
                  file=self.out)
        for line in self.tail:
            self.out.write(line)
        self.finished = True
        self.flush()
