import json
import re

from .config import non_empty_text
from .pr import field
from .process import LadderError, plain


def review_logins(project, bots):
    logins = bots if bots is not None else (project.review.get("wait_for", []) if project else [])
    if not logins:
        raise LadderError('no reviewer set: add [review] wait_for = ["login"] to ladder.toml or pass --bot')
    unique = {}
    for login in logins:
        unique.setdefault(login.strip().casefold(), login.strip())
    return unique


def parse_reviews(answer):
    """Validate all pages, including adjacent arrays emitted by gh --paginate."""
    decoder = json.JSONDecoder()
    remaining = answer.strip()
    reviews = []
    if not remaining:
        raise LadderError("gh returned bad JSON: empty reviews answer")
    while remaining:
        try:
            page, end = decoder.raw_decode(remaining)
        except json.JSONDecodeError as error:
            raise LadderError(f"gh returned bad JSON: {error}") from error
        if not isinstance(page, list):
            raise LadderError("gh returned reviews that are not an array")
        for review in page:
            for path in ("user/login", "commit_id", "state"):
                if not non_empty_text(field(review, path)):
                    raise LadderError(f"gh returned review with missing or invalid {path.replace('/', '.')}")
            reviews.append(review)
        remaining = remaining[end:].lstrip()
    return reviews


def finished_review_states(reviews, head):
    return {review["user"]["login"].casefold(): review["state"]
            for review in reviews
            if review["commit_id"] == head and review["state"] != "PENDING"}


def review_status(head, reviewers, states, waiting):
    if waiting:
        return f"{head[:7]}: waiting for {', '.join(waiting)}"
    return f"{head[:7]}: done: " + ", ".join(
        f"{login} ({states[key]})" for key, login in reviewers.items())


def fetch_review_states(number, runner):
    head = runner.capture(["gh", "pr", "view", str(number), "--json",
                           "headRefOid", "-q", ".headRefOid"]).strip()
    if not re.fullmatch(r"[0-9a-fA-F]+", head):
        raise LadderError("gh returned a missing or invalid head commit")
    answer = runner.capture(["gh", "api", f"repos/{{owner}}/{{repo}}/pulls/{number}/reviews",
                             "--paginate"])
    return head, finished_review_states(parse_reviews(answer), head)


class ReviewWait:
    def __init__(self, clock, sleep):
        self.clock = clock
        self.sleep = sleep

    def wait(self, args, runner, out):
        # Keep the poll lifecycle together so head changes, status and timeout share 1 snapshot.
        deadline = self.clock() + args.timeout_mins * 60
        last_head, last_line = None, None
        while True:
            head, states = fetch_review_states(args.number, runner)
            waiting = [login for key, login in args.reviewers.items() if key not in states]
            if last_head is not None and head != last_head:
                print(f"head changed: {last_head[:7]} -> {head[:7]}", file=out, flush=True)
            line = review_status(head, args.reviewers, states, waiting)
            if head != last_head or line != last_line:
                print(plain(line), file=out, flush=True)
            last_head, last_line = head, line
            if not waiting:
                return
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise LadderError(f"timed out after {args.timeout_mins} min; still waiting for "
                                  f"{', '.join(waiting)} on {head[:7]}")
            self.sleep(min(30, remaining))
