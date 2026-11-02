"""The simulated human: a person who asked for a project and holds a hidden brief.

Each reply is one isolated one-shot `claude -p` session started in its own
folder, on a cheap model, with the launch.py environment. The session sees the
message it answers, the brief items that message names, and, in the Compass arm,
the Compass README. It does not see the rest of the brief.

An item is named by a message when the item's name occurs in the message,
ignoring case. A message naming at least one item is a revealing question and
uses one unit of the question budget, however many items it names; once the
budget is spent such a question is answered "decide yourself" without a
session. Gate approvals and continue messages name no item, are always passed
to a session and use no budget. The count of used questions is kept in the
state file, so every process that reads the same file sees it.

The session's result text is a JSON object `{"text": str, "done": bool}`. Text
that is not such an object is the reply text with `done` false; `done` is true
only for the JSON value true.

Every session is recorded as a role `human` row. Its tokens never reach a
build's row.

    python human.py answer --state-file FILE

reads `{"questions": [...]}` from stdin and prints `{"answers": {...}}`; the
state file carries the settings the instance was built with.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import launch
import records

DECIDE_YOURSELF = "decide yourself"
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_BUDGET = 12

_FENCE = re.compile(r"^\s*```[A-Za-z]*\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


@dataclass
class Reply:
    text: str
    done: bool = False
    events: tuple = ()
    outcome: str = launch.DONE


def parse_reply(text):
    """(reply text, done) from the result text of a human session."""
    candidate = text.strip()
    fenced = _FENCE.match(candidate)
    if fenced:
        candidate = fenced.group(1)
    try:
        value = json.loads(candidate)
    except (ValueError, RecursionError):
        return text, False
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return value["text"], value.get("done") is True
    return text, False


def _result_text(events):
    for event in reversed(events):
        if event.get("type") == "result":
            value = event.get("result")
            return value if isinstance(value, str) else ""
    return ""


def _atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(data))
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


class SimulatedHuman:
    def __init__(
        self,
        brief,
        *,
        folder,
        repo_root,
        arm,
        state_file,
        private_root=None,
        claude_cmd=None,
        budget=DEFAULT_BUDGET,
        readme=None,
        model=DEFAULT_MODEL,
        timeout=None,
    ):
        if arm not in records.ARMS:
            raise ValueError(f"arm is not one of {', '.join(records.ARMS)}")
        self.brief = brief
        self.folder = Path(folder)
        self.repo_root = Path(repo_root)
        self.arm = arm
        self.state_file = Path(state_file)
        self.private_root = Path(private_root) if private_root is not None else None
        self.claude_cmd = list(claude_cmd) if claude_cmd else None
        self.budget = budget
        self.readme = readme
        self.model = model
        self.timeout = timeout
        if records._inside_work_tree(self.state_file.parent):
            raise records.Refused("the simulated human's state stays outside git work trees")
        self._write_state(self.questions_used)

    @classmethod
    def from_state_file(cls, state_file):
        """The instance whose settings `state_file` carries."""
        state = json.loads(Path(state_file).read_text(encoding="utf-8"))
        config = state["config"]
        return cls(
            config["brief"],
            folder=config["folder"],
            repo_root=config["repo_root"],
            arm=config["arm"],
            state_file=state_file,
            private_root=config["private_root"],
            claude_cmd=config["claude_cmd"],
            budget=config["budget"],
            readme=config["readme"],
            model=config["model"],
            timeout=config["timeout"],
        )

    @property
    def answer_command(self):
        return [sys.executable, str(Path(__file__).resolve()), "answer", "--state-file", str(self.state_file)]

    @property
    def questions_used(self):
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0
        used = state.get("used") if isinstance(state, dict) else None
        return used if isinstance(used, int) and not isinstance(used, bool) and used >= 0 else 0

    def _write_state(self, used):
        _atomic_write(self.state_file, {
            "used": used,
            "config": {
                "brief": self.brief,
                "folder": str(self.folder),
                "repo_root": str(self.repo_root),
                "arm": self.arm,
                "private_root": str(self.private_root) if self.private_root is not None else None,
                "claude_cmd": self.claude_cmd,
                "budget": self.budget,
                "readme": self.readme,
                "model": self.model,
                "timeout": self.timeout,
            },
        })

    def named_items(self, message):
        """The brief items whose name occurs in `message`, ignoring case."""
        lowered = message.lower()
        return [
            item for item in self.brief.get("items", [])
            if isinstance(item.get("name"), str) and item["name"].strip() and item["name"].lower() in lowered
        ]

    def _prompt(self, message, named):
        parts = [
            "You are a person who asked an AI assistant to build a software project for you. "
            "You are answering the assistant's latest message as that person.",
            "You have no knowledge of how the project should be built. Never propose a design, a library, "
            "a file layout or code; say what you want, not how to make it.",
        ]
        if self.arm == "compass" and self.readme:
            parts.append(
                "The assistant works with Compass, a plugin you know from this guide, "
                "including its commands:\n\n" + self.readme
            )
        if named:
            wishes = "\n".join(f"- {item['name']}: {item.get('detail', '')}" for item in named)
            parts.append("What you want, as far as the message asks about it:\n" + wishes)
        else:
            parts.append(
                f"The message asks for nothing you have a stated wish about. If it asks what you want, "
                f"answer \"{DECIDE_YOURSELF}\". If it asks you to approve a step or to continue, "
                "approve it and tell the assistant to continue."
            )
        parts.append(
            "Set \"done\" to true only when the assistant reports the whole project built and you ask for "
            "nothing more; otherwise false."
        )
        parts.append(
            "Reply with one JSON object and nothing else: {\"text\": \"<your message>\", \"done\": false}"
        )
        parts.append("The assistant's latest message:\n<<<\n" + message + "\n>>>")
        return "\n\n".join(parts)

    def _session(self, message, named):
        result = launch.run_session(
            self.folder,
            self._prompt(message, named),
            repo_root=self.repo_root,
            private_root=self.private_root,
            plugin=False,
            claude_cmd=self.claude_cmd,
            extra_args=["--model", self.model],
            timeout=self.timeout,
        )
        records.record_session(
            result.events, role="human", outcome=result.status, arm=self.arm, private_root=self.private_root,
        )
        events = tuple(result.events)
        if result.status != launch.DONE:
            return Reply(text="", done=False, events=events, outcome=result.status)
        text, done = parse_reply(_result_text(result.events))
        return Reply(text=text, done=done, events=events, outcome=launch.DONE)

    def reply(self, message):
        """The simulated human's answer to `message`."""
        named = self.named_items(message)
        if named:
            used = self.questions_used
            if used >= self.budget:
                return Reply(text=DECIDE_YOURSELF)
            self._write_state(used + 1)
        return self._session(message, named)

    def answer_questions(self, questions):
        """{question text: answer text} for the questions of one picker call.

        Raises RuntimeError when a human session ends in a failure or a usage limit.
        """
        answers = {}
        for question in questions:
            text = question.get("question", "")
            lines = [text]
            for option in question.get("options", []):
                label = option.get("label", "")
                description = option.get("description")
                lines.append(f"- {label}" + (f": {description}" if description else ""))
            if question.get("multiSelect"):
                lines.append("(several options may be chosen; separate the labels with commas)")
            reply = self.reply("\n".join(lines))
            if reply.outcome != launch.DONE:
                raise RuntimeError(f"the simulated human's session ended with {reply.outcome}")
            answers[text] = reply.text or DECIDE_YOURSELF
        return answers


def main(argv=None, stdin_text=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    verbs = parser.add_subparsers(dest="verb", required=True)
    answer = verbs.add_parser("answer", help="answer the questions read from stdin")
    answer.add_argument("--state-file", required=True)
    args = parser.parse_args(argv)

    text = sys.stdin.read() if stdin_text is None else stdin_text
    try:
        questions = json.loads(text)["questions"]
        who = SimulatedHuman.from_state_file(args.state_file)
        answers = who.answer_questions(questions)
    except Exception as error:
        sys.stderr.write(f"human answer failed: {error}\n")
        return 1
    sys.stdout.write(json.dumps({"answers": answers}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
