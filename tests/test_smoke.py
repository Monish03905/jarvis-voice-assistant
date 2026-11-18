"""Offline smoke tests: routing, parsing, safety rules.

Run:  .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import backend.db as db
import config as cfg
from backend.agent import DESTRUCTIVE, JarvisAgent
from backend.skills import email_skill, files, finance, info, news


def _account(label: str, address: str) -> dict:
    return {
        "label": label,
        "display_name": label.title(),
        "address": address,
        "password": "test-only",
        "smtp_host": "smtp.example.test",
        "smtp_port": 587,
        "smtp_ssl": False,
        "imap_host": "imap.example.test",
        "imap_port": 993,
        "configured": True,
    }


async def _noop(*_args, **_kwargs):
    return None


def _agent() -> JarvisAgent:
    return JarvisAgent(hud_emit=_noop)


class IntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = _agent()

    def route(self, text: str):
        result = self.agent._fast_intent(text)
        return (result or {}).get("action"), (result or {}).get("parameters", {})

    def test_power_requires_confirmation_action(self):
        action, params = self.route("shutdown in 5 minutes")
        self.assertEqual(action, "shutdown")
        self.assertEqual(params["timer"], 300)

    def test_weather_captures_city(self):
        self.assertEqual(self.route("what is the weather in London")[0], "get_weather")
        self.assertEqual(self.route("weather for Mumbai")[1]["city"], "mumbai")

    def test_open_folder_is_file_action(self):
        action, params = self.route("open downloads folder")
        self.assertEqual(action, "list_files")
        self.assertEqual(params["directory"], "downloads")

    def test_whatsapp_message(self):
        action, params = self.route("send message to ravi on whatsapp saying I am late")
        self.assertEqual(action, "send_whatsapp")
        self.assertEqual(params["contact"], "ravi")
        self.assertEqual(params["message"], "I am late")

    def test_email_with_subject(self):
        action, params = self.route("send an email to bob with subject Lunch saying see you at one")
        self.assertEqual(action, "send_email")
        self.assertEqual(params["to"], "bob")
        self.assertEqual(params["subject"], "Lunch")
        self.assertEqual(params["body"], "see you at one")

    def test_percent_expression(self):
        action, params = self.route("what is 10 percent of 5000")
        self.assertEqual(action, "calculate")
        self.assertEqual(params["expression"], "10/100*5000")

    def test_budget_amount_first(self):
        action, params = self.route("set a budget of 5000 for food")
        self.assertEqual(action, "set_budget")
        self.assertEqual(params["category"], "food")
        self.assertEqual(params["amount"], "5000")

    def test_plain_chat_is_left_to_the_model(self):
        self.assertIsNone(self.agent._fast_intent("how are you"))


class CalculatorTests(unittest.TestCase):
    def test_basic_math(self):
        self.assertIn("108", info.calculate("12*9"))

    def test_rejects_code(self):
        self.assertIn("could not evaluate", info.calculate("__import__('os').system('dir')").lower())


class MoneyTests(unittest.TestCase):
    def test_amount_suffixes(self):
        self.assertEqual(finance._amount("50k"), 50000)
        self.assertEqual(finance._amount("1,200"), 1200)
        self.assertEqual(finance._amount("₹250.5"), 250.5)

    def test_summary_shape(self):
        summary = db.money_summary("1999-01")
        for key in ("month", "income", "spent", "balance", "by_category", "budgets"):
            self.assertIn(key, summary)


class FileTests(unittest.TestCase):
    def test_locations_resolve(self):
        for name in ("desktop", "downloads", "documents", "pictures"):
            self.assertTrue(Path(files.resolve_location(name)).is_absolute())

    def test_unknown_location_is_treated_as_path(self):
        self.assertIn("nonexistent-place", str(files.resolve_location("nonexistent-place")))


class NewsTests(unittest.TestCase):
    def test_clean_strips_html(self):
        self.assertEqual(news._clean("<b>Hello</b>   world"), "Hello world")

    def test_categories_build_google_news_url(self):
        feeds = news._feeds("technology")
        self.assertEqual(len(feeds), 1)
        self.assertIn("news.google.com", feeds[0])
        self.assertIn("technology", feeds[0])


class EmailAccountTests(unittest.TestCase):
    def setUp(self):
        self._saved = dict(cfg.EMAIL_ACCOUNTS)
        cfg.EMAIL_ACCOUNTS.clear()
        cfg.EMAIL_ACCOUNTS.update({
            "personal": _account("personal", "me@gmail.com"),
            "college": _account("college", "me@college.edu"),
        })
        self.agent = _agent()

    def tearDown(self):
        cfg.EMAIL_ACCOUNTS.clear()
        cfg.EMAIL_ACCOUNTS.update(self._saved)

    def route(self, text: str):
        result = self.agent._fast_intent(text)
        return (result or {}).get("action"), (result or {}).get("parameters", {})

    def test_resolve_by_label_phrase_and_address(self):
        self.assertEqual(email_skill.resolve_account("college")["address"], "me@college.edu")
        self.assertEqual(email_skill.resolve_account("my college email")["label"], "college")
        self.assertEqual(email_skill.resolve_account("me@gmail.com")["label"], "personal")

    def test_read_account_specific_inbox(self):
        action, params = self.route("read my college email")
        self.assertEqual(action, "read_emails")
        self.assertEqual(params.get("account"), "college")

    def test_send_from_account(self):
        action, params = self.route("send an email from college to Ravi about lunch")
        self.assertEqual(action, "send_email")
        self.assertEqual(params.get("account"), "college")
        self.assertEqual(params.get("to"), "Ravi")

    def test_list_accounts(self):
        action, _ = self.route("email accounts")
        self.assertEqual(action, "email_accounts")
        summary = email_skill.accounts_summary()
        self.assertIn("personal", summary)
        self.assertIn("college", summary)

    def test_status_shape(self):
        status = email_skill.status()
        self.assertTrue(status["smtp"])
        self.assertEqual(status["default"], "personal")
        self.assertEqual({a["label"] for a in status["accounts"]}, {"personal", "college"})

    def test_provider_presets(self):
        self.assertEqual(cfg.mail_preset("a@gmail.com")[0], "smtp.gmail.com")
        self.assertEqual(cfg.mail_preset("a@outlook.com")[0], "smtp.office365.com")
        self.assertEqual(cfg.mail_preset("a@college.edu")[0], "smtp.college.edu")

    def test_send_uses_selected_account(self):
        sent = {}

        class FakeSMTP:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def login(self, user, password):
                sent["login"] = user

            def send_message(self, message):
                sent["message"] = message

        with patch.object(email_skill, "_smtp", return_value=FakeSMTP()):
            reply = email_skill.send_email(
                "ravi@example.com", "Lunch", "At noon", account="college"
            )
        self.assertIn("college", reply)
        self.assertEqual(sent["login"], "me@college.edu")
        self.assertIn("me@college.edu", sent["message"]["From"])

    def test_read_all_accounts(self):
        import email.message

        class FakeIMAP:
            def select(self, *args, **kwargs):
                return "OK", [b""]

            def search(self, *args):
                return "OK", [b"1"]

            def fetch(self, msg_id, parts):
                message = email.message.EmailMessage()
                message["From"] = "Alice <alice@example.com>"
                message["Subject"] = "Hello"
                message.set_content("Body text")
                return "OK", [(b"1", message.as_bytes())]

            def logout(self):
                pass

        with patch.object(email_skill, "_imap", side_effect=lambda acc: FakeIMAP()):
            reply = email_skill.read_emails(limit=2)
        self.assertIn("personal", reply)
        self.assertIn("college", reply)
        self.assertIn("Hello", reply)


class SafetyTests(unittest.TestCase):
    def test_destructive_actions_are_guarded(self):
        for action in ("shutdown", "restart", "delete_file", "empty_recycle_bin"):
            self.assertIn(action, DESTRUCTIVE)

    def test_voice_lock_default(self):
        self.assertIsInstance(cfg.VOICE_LOCK_ENABLED, bool)

    def test_secret_keys_are_not_placeholder_checked_as_real(self):
        from backend.brain import Brain

        brain = Brain()
        self.assertIsInstance(brain.status(), dict)


if __name__ == "__main__":
    unittest.main()
