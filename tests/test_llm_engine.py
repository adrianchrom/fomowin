import unittest
from monitors.llm_engine import llm_engine

class TestLLMEngine(unittest.TestCase):
    def setUp(self):
        llm_engine.clear_history()

    def test_empty_prompt(self):
        resp = llm_engine.generate_response("")
        self.assertIn("Wprowadź treść pytania", resp)

    def test_wyceny_prompt(self):
        resp = llm_engine.generate_response("Napisz e-mail z wyceną dla klienta")
        self.assertIn("Wycena", resp)
        self.assertIn("Dzień dobry", resp)

    def test_krypto_prompt(self):
        resp = llm_engine.generate_response("Jakie jest ryzyko na rynku krypto?")
        self.assertIn("FOMO", resp)
        self.assertIn("bezpieczeństwa", resp)

    def test_budzet_prompt(self):
        resp = llm_engine.generate_response("Zoptymalizuj wydatki i budżet")
        self.assertIn("WYDATKI", resp)

    def test_process_chat_history(self):
        res = llm_engine.process_chat("Cześć!")
        self.assertTrue(res["success"])
        self.assertEqual(res["history_length"], 2)

        llm_engine.clear_history()
        self.assertEqual(len(llm_engine.chat_history), 0)

if __name__ == '__main__':
    unittest.main()
