import json
import re

from .process import LadderError, redact


THREADS_QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes {
          isResolved
          isOutdated
          path
          line
          comments(first: 50) { nodes { author { login } body url } }
        }
      }
    }
  }
}"""


def parse_threads(answer):
    try:
        payload = json.loads(answer)
    except json.JSONDecodeError as error:
        raise LadderError(f"gh returned bad JSON: {error}") from error
    nodes = field(payload, "data/repository/pullRequest/reviewThreads/nodes")
    if not isinstance(nodes, list):
        raise LadderError("no review threads in gh's answer; is the PR number right?")
    return [thread_from(node) for node in nodes]


def field(node, path):
    for key in path.split("/"):
        node = node.get(key) if isinstance(node, dict) else None
    return node


def text(node, path):
    content = field(node, path)
    return content if isinstance(content, str) else ""


def thread_from(node):
    line = field(node, "line")
    comments = field(node, "comments/nodes")
    return {"path": text(node, "path"),
            "line": line if type(line) is int and 0 <= line < 2**64 else None,
            "isResolved": field(node, "isResolved") is True,
            "isOutdated": field(node, "isOutdated") is True,
            "comments": {"nodes": [
                {"author": {"login": text(comment, "author/login")},
                 "body": text(comment, "body"), "url": text(comment, "url")}
                for comment in (comments if isinstance(comments, list) else [])]}}


def summary(body):
    rest = re.sub(r"<!--.*?(?:-->|$)", "", body, flags=re.S)
    plain, depth = [], 0
    while (start := rest.find("<")) >= 0:
        end = rest.find(">", start)
        if end < 0:
            break
        if depth == 0:
            plain.append(rest[:start])
        tag = rest[start:end + 1]
        if tag.startswith("<details"):
            depth += 1
        elif tag.startswith("</details"):
            depth = max(0, depth - 1)
        rest = rest[end + 1:]
    if depth == 0:
        plain.append(rest)
    lines = (line.strip() for line in "".join(plain).replace("**", "").splitlines())
    return "\n".join([line for line in lines if line][:3])


def thread_location(thread):
    location = thread["path"] + (f":{thread['line']}" if thread['line'] is not None else "")
    location += " [resolved]" if thread["isResolved"] else ""
    location += " [outdated]" if thread["isOutdated"] else ""
    return location


def render_threads(number, threads, all_threads, full):
    opened = sum(not thread["isResolved"] for thread in threads)
    lines = [f"PR #{number}: {opened} unresolved of {len(threads)} threads"]
    for thread in sorted(threads, key=lambda t: (t["isResolved"], t["path"],
                                                t["line"] is not None, t["line"] or 0)):
        if thread["isResolved"] and not all_threads:
            continue
        lines.extend(["", thread_location(thread)])
        for comment in thread["comments"]["nodes"]:
            lines.append(f"  {comment['author']['login']}:")
            body = comment["body"].strip() if full else summary(comment["body"])
            lines.extend("    " + line for line in body.splitlines())
            lines.append("    " + comment["url"])
    return "\n".join(lines) + "\n"


def comments(args, runner, out):
    answer = runner.capture(["gh", "api", "graphql", "-F", "owner={owner}", "-F", "name={repo}",
                             "-F", f"number={args.number}", "-f", f"query={THREADS_QUERY}"])
    print(redact(render_threads(args.number, parse_threads(answer), args.all, args.full)), file=out, end="")
