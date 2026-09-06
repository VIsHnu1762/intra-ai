"""Unit tests for Intra AI Agent Registry and Agora Agent Studio Mapping."""

import unittest
from unittest.mock import patch

from app.agents import (
    ALEX_AGENT_ID,
    ActionType,
    AgentProfile,
    AgentRegistry,
    AgoraAgentMapping,
    NextAction,
    agent_registry,
)
from app.core.exceptions import AgentNotFoundError, AgoraConfigurationError
from app.core.config import settings
from app.models.enums import DifficultyLevel


class TestAgentRegistry(unittest.TestCase):
    """Test suite verifying Agent Registry contracts, Alex persona, and Agora runtime mappings."""

    def setUp(self) -> None:
        """Ensure the global registry is reset before each test."""
        # These tests exercise legacy defaults; local shared voice-pipeline
        # configuration is covered separately by the dispatch contract tests.
        common_pipeline_patch = patch.object(settings, "AGORA_CUSTOM_LLM_PIPELINE_ID", "")
        common_pipeline_patch.start()
        self.addCleanup(common_pipeline_patch.stop)
        agent_registry.reset()

    # ── TEST 1 — Resolve Alex ──────────────────────────────────────────────
    def test_01_resolve_alex(self) -> None:
        """Given agent_id = 'alex', the registry returns Alex's profile."""
        profile = agent_registry.get_profile("alex")
        self.assertIsNotNone(profile)
        self.assertIsInstance(profile, AgentProfile)
        self.assertEqual(profile.agent_id, "alex")

        # Also verify case-insensitivity
        profile_upper = agent_registry.get_profile("ALEX")
        self.assertEqual(profile_upper.agent_id, "alex")

    # ── TEST 2 — Alex identity ──────────────────────────────────────────────
    def test_02_alex_identity(self) -> None:
        """Verify agent_id == 'alex', display_name == 'Alex', and role identifies technical interviewer."""
        profile = agent_registry.get_profile("alex")

        self.assertEqual(profile.agent_id, "alex")
        self.assertEqual(profile.display_name, "Alex")
        self.assertIn("Technical Manager", profile.role)
        self.assertIn("technical interviewer", profile.description.lower())
        self.assertEqual(profile.questioning_style, "adaptive technical interviewer")
        self.assertIn("Alex", profile.instructions)
        self.assertIn("Senior Technical Manager", profile.instructions)

    # ── TEST 3 — Alex competencies ─────────────────────────────────────────
    def test_03_alex_competencies(self) -> None:
        """Verify Alex owns the expected technical competency areas."""
        profile = agent_registry.get_profile("alex")
        focal = set(profile.focal_competencies)

        expected_competencies = [
            "system_design",
            "software_architecture",
            "coding_problem_solving",
            "scalability",
            "technical_decision_making",
            "debugging",
            "technical_depth",
        ]

        for comp in expected_competencies:
            self.assertIn(
                comp,
                focal,
                f"Expected competency '{comp}' not found in Alex focal competencies: {profile.focal_competencies}",
            )

        # Verify allowed actions include canonical action types
        self.assertIn(ActionType.ASK_QUESTION, profile.allowed_actions)
        self.assertIn(ActionType.SWITCH_AGENT, profile.allowed_actions)
        self.assertIn(ActionType.COMPLETE, profile.allowed_actions)

    # ── TEST 4 — Agora mapping ──────────────────────────────────────────────
    def test_04_alex_agora_mapping(self) -> None:
        """Verify that Alex resolves to the configured Agora project/pipeline mapping."""
        mapping = agent_registry.get_agora_mapping("alex")

        self.assertIsInstance(mapping, AgoraAgentMapping)
        self.assertEqual(mapping.project_id, "acbcfc97ea094e3681d46fe8da21e4d1")
        self.assertEqual(mapping.pipeline_id, "eb714d82ec524f14981e5b5f5108cbd1")
        self.assertEqual(mapping.asr_vendor, "deepgram")
        self.assertEqual(mapping.asr_model, "nova-3")
        self.assertEqual(mapping.llm_vendor, "openai")
        self.assertEqual(mapping.llm_model, "intra-ai")
        self.assertIsNotNone(mapping.llm_url)
        self.assertIn("/api/v1/chat/completions", mapping.llm_url)
        self.assertEqual(mapping.tts_vendor, "openai")
        self.assertEqual(mapping.tts_model, "tts-1")
        self.assertEqual(mapping.tts_voice, "echo")
        self.assertTrue(mapping.filler_words_enabled)
        self.assertEqual(mapping.filler_words_threshold_ms, 1500)

        # Also test composite helper get_agent
        prof, mapp = agent_registry.get_agent("alex")
        self.assertEqual(prof.agent_id, "alex")
        self.assertEqual(mapp.project_id, "acbcfc97ea094e3681d46fe8da21e4d1")

    # ── TEST 5 — Missing configuration ──────────────────────────────────────
    def test_05_missing_configuration_produces_deterministic_error(self) -> None:
        """Verify that missing required Agora configuration produces a clear, deterministic error."""
        custom_registry = AgentRegistry(register_defaults=False)

        # Register agent with no Agora mapping
        mock_profile = AgentProfile(
            agent_id="test_agent",
            display_name="Test Agent",
            role="Interviewer",
            description="Test Interviewer",
            focal_competencies=["general"],
            questioning_style="probing",
            instructions="Test instructions",
        )
        custom_registry.register(mock_profile, agora_mapping=None)

        # Profile succeeds
        self.assertEqual(custom_registry.get_profile("test_agent").agent_id, "test_agent")

        # Agora mapping fails with AgoraConfigurationError
        with self.assertRaises(AgoraConfigurationError) as ctx:
            custom_registry.get_agora_mapping("test_agent")
        self.assertIn("does not have a configured Agora Agent Studio mapping", str(ctx.exception))

        # Register agent with empty project_id
        with self.assertRaises(ValueError):
            AgoraAgentMapping(project_id="", pipeline_id="valid-pipe")

        with self.assertRaises(ValueError):
            AgoraAgentMapping(project_id="valid-proj", pipeline_id="   ")

    # ── TEST 6 — N-agent extensibility ─────────────────────────────────────
    def test_06_n_agent_extensibility(self) -> None:
        """Prove that another logical agent (e.g. Jordan) can be registered/resolved without changing routing logic."""
        jordan_profile = AgentProfile(
            agent_id="jordan",
            display_name="Jordan",
            role="Product Lead",
            description="Product Lead and interviewer at Intra AI evaluating customer impact and product sense.",
            focal_competencies=[
                "product_sense",
                "customer_impact",
                "trade_off_analysis",
                "metrics_and_roi",
            ],
            questioning_style="empathetic product inquiry",
            instructions="You are Jordan, Product Lead at Intra AI...",
            min_difficulty=DifficultyLevel.EASY,
            max_difficulty=DifficultyLevel.HARD,
            allowed_actions=[ActionType.ASK_QUESTION, ActionType.SWITCH_AGENT, ActionType.COMPLETE],
        )
        jordan_mapping = AgoraAgentMapping(
            project_id="jordan-agora-project-id",
            pipeline_id="jordan-agora-pipeline-id",
            tts_voice="alloy",
        )

        agent_registry.register(jordan_profile, jordan_mapping)

        # Verify Jordan is resolved
        self.assertTrue(agent_registry.has_agent("jordan"))
        resolved_profile = agent_registry.get_profile("jordan")
        self.assertEqual(resolved_profile.display_name, "Jordan")
        self.assertEqual(resolved_profile.role, "Product Lead")
        self.assertIn("customer_impact", resolved_profile.focal_competencies)

        # Verify Jordan's Agora mapping
        resolved_mapping = agent_registry.get_agora_mapping("jordan")
        self.assertEqual(resolved_mapping.project_id, "jordan-agora-project-id")
        self.assertEqual(resolved_mapping.pipeline_id, "jordan-agora-pipeline-id")
        self.assertEqual(resolved_mapping.tts_voice, "alloy")

        # Verify list of registered agent IDs contains both alex and jordan
        all_ids = agent_registry.list_agent_ids()
        self.assertIn("alex", all_ids)
        self.assertIn("jordan", all_ids)

    # ── TEST 7 — Unknown agent ──────────────────────────────────────────────
    def test_07_unknown_agent_fails_predictably(self) -> None:
        """Resolving an unknown agent ID should fail clearly and predictably with AgentNotFoundError."""
        with self.assertRaises(AgentNotFoundError) as ctx:
            agent_registry.get_profile("non_existent_agent")
        self.assertIn("non_existent_agent", str(ctx.exception))

        with self.assertRaises(AgentNotFoundError):
            agent_registry.get_agora_mapping("non_existent_agent")

        self.assertFalse(agent_registry.has_agent("non_existent_agent"))

    # ── Canonical NextAction contract tests ────────────────────────────────
    def test_08_canonical_next_action_contract(self) -> None:
        """Verify the canonical NextAction contract uses only ASK_QUESTION, SWITCH_AGENT, COMPLETE."""
        action_ask = NextAction(
            action=ActionType.ASK_QUESTION,
            target_agent_id="alex",
            competency="scalability",
            difficulty=DifficultyLevel.HARD,
            question_text="How would you partition Redis keys to avoid hot shards?",
            rationale="Candidate demonstrated strong knowledge; probing sharding depth.",
        )
        self.assertEqual(action_ask.action, ActionType.ASK_QUESTION)
        self.assertEqual(action_ask.difficulty, DifficultyLevel.HARD)

        action_switch = NextAction(
            action=ActionType.SWITCH_AGENT,
            target_agent_id="jordan",
            competency="customer_impact",
            rationale="Technical competencies covered; transitioning to Product Lead.",
            metadata={"handoff_note": "Candidate scaled payment API."},
        )
        self.assertEqual(action_switch.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action_switch.target_agent_id, "jordan")

        action_complete = NextAction(
            action=ActionType.COMPLETE,
            rationale="All interview competencies assessed across technical and product domains.",
        )
        self.assertEqual(action_complete.action, ActionType.COMPLETE)

    # ── TEST 9 — Agora Join Payload Generation ─────────────────────────────
    def test_09_agora_join_payload_generation(self) -> None:
        """Verify that to_agora_join_payload outputs custom LLM URL and intra-ai model."""
        profile, mapping = agent_registry.get_agent("alex")
        payload = mapping.to_agora_join_payload(
            channel_name="test-interview-123",
            user_uid=100,
            agent_rtc_uid=1001,
            agent_token="test-token",
            system_prompt=profile.instructions,
            greeting="Hello Alex here.",
        )

        self.assertEqual(payload["channel_name"], "test-interview-123")
        self.assertEqual(payload["user_uid"], "100")
        self.assertEqual(payload["agent_rtc_uid"], "1001")
        self.assertEqual(payload["agent_token"], "test-token")

        props = payload["properties"]
        self.assertEqual(props["pipeline_id"], "eb714d82ec524f14981e5b5f5108cbd1")
        self.assertEqual(props["asr"]["vendor"], "deepgram")
        self.assertEqual(props["asr"]["params"]["model"], "nova-3")
        self.assertEqual(props["tts"]["vendor"], "openai")

        llm = props["llm"]
        self.assertEqual(llm["vendor"], "openai")
        self.assertEqual(llm["params"]["model"], "intra-ai")
        self.assertIsNotNone(llm["url"])
        self.assertIn("/api/v1/chat/completions", llm["url"])
        self.assertNotEqual(llm["url"], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(len(llm["system_messages"]), 1)
        self.assertIn("Alex", llm["system_messages"][0]["content"])
        self.assertEqual(llm["greeting_message"], "Hello Alex here.")

    # ── TEST 10 — Jordan Default Profile & Mapping Resolution ───────────────
    def test_10_jordan_default_profile_and_mapping(self) -> None:
        """Verify Jordan is registered by default with exact Agent Studio profile and mapping."""
        self.assertTrue(agent_registry.has_agent("jordan"))
        profile = agent_registry.get_profile("jordan")
        mapping = agent_registry.get_agora_mapping("jordan")

        # Profile checks
        self.assertEqual(profile.agent_id, "jordan")
        self.assertEqual(profile.display_name, "Jordan")
        self.assertEqual(profile.role, "Senior Product Manager")
        self.assertIn("product_sense", profile.focal_competencies)
        self.assertIn("customer_impact", profile.focal_competencies)
        self.assertIn("prioritization", profile.focal_competencies)
        self.assertIn("trade_off_decisions", profile.focal_competencies)
        self.assertIn("Senior Product Manager", profile.instructions)

        # Mapping checks
        self.assertEqual(mapping.pipeline_id, "642bb4345fa244099a78a50cede2d7d3")
        self.assertEqual(mapping.asr_vendor, "deepgram")
        self.assertEqual(mapping.asr_model, "nova-3")
        self.assertEqual(mapping.asr_language, "en")
        self.assertEqual(mapping.llm_vendor, "openai")
        self.assertEqual(mapping.llm_model, "intra-ai")
        self.assertEqual(mapping.tts_vendor, "openai")
        self.assertEqual(mapping.tts_model, "tts-1")
        self.assertEqual(mapping.tts_voice, "nova")
        self.assertEqual(mapping.tts_speed, 1.0)
        self.assertEqual(mapping.turn_detection, "default_vad")
        self.assertEqual(mapping.vad_silence_duration_ms, 400)
        self.assertEqual(mapping.vad_speech_threshold, 0.4)
        self.assertEqual(mapping.vad_prefix_padding_ms, 600)
        self.assertEqual(mapping.vad_interrupt_duration_ms, 120)
        self.assertEqual(mapping.vad_speaking_interrupt_duration_ms, 120)
        self.assertTrue(mapping.filler_words_enabled)
        self.assertEqual(mapping.filler_words_threshold_ms, 1500)
        self.assertIn("Please wait.", mapping.filler_phrases)
        self.assertIn("Hi, I'm Jordan, the Product Manager at Intra AI", mapping.greeting)

    # ── TEST 11 — Jordan Agora Join Payload Generation ──────────────────────
    def test_11_jordan_agora_join_payload_generation(self) -> None:
        """Verify Jordan join payload contains Jordan's pipeline ID, nova voice, greeting, and custom LLM."""
        profile, mapping = agent_registry.get_agent("jordan")
        payload = mapping.to_agora_join_payload(
            channel_name="interview-prod-001",
            user_uid=200,
            agent_rtc_uid=1002,
            agent_token="jordan-rtc-token",
            system_prompt=profile.instructions,
            greeting=mapping.greeting,
        )

        self.assertEqual(payload["channel_name"], "interview-prod-001")
        self.assertEqual(payload["user_uid"], "200")
        self.assertEqual(payload["agent_rtc_uid"], "1002")
        self.assertEqual(payload["agent_token"], "jordan-rtc-token")

        props = payload["properties"]
        self.assertEqual(props["pipeline_id"], "642bb4345fa244099a78a50cede2d7d3")
        self.assertEqual(props["tts"]["params"]["voice"], "nova")
        self.assertEqual(props["asr"]["vendor"], "deepgram")
        self.assertEqual(props["asr"]["params"]["model"], "nova-3")

        llm = props["llm"]
        self.assertEqual(llm["vendor"], "openai")
        self.assertEqual(llm["params"]["model"], "intra-ai")
        self.assertIsNotNone(llm["url"])
        self.assertIn("/api/v1/chat/completions", llm["url"])
        self.assertIn("Hi, I'm Jordan, the Product Manager at Intra AI", llm["greeting_message"])
        self.assertIn("Senior Product Manager", llm["system_messages"][0]["content"])

        vad = props["vad"]
        self.assertEqual(vad["mode"], "default_vad")
        self.assertEqual(vad["silence_duration_ms"], 400)
        self.assertEqual(vad["speech_threshold"], 0.4)

        filler = props["filler_words"]
        self.assertTrue(filler["enable"])
        self.assertEqual(filler["wait_time"], 1500)
        phrases = filler.get("content", {}).get("static_config", {}).get("phrases", [])
        self.assertIn("Please wait.", phrases)

    # ── TEST 12 — Alex vs Jordan Mapping Comparison ────────────────────────
    def test_12_alex_vs_jordan_mapping_differences(self) -> None:
        """Verify the distinct runtime differences between Alex (Technical) and Jordan (Product)."""
        alex_prof, alex_map = agent_registry.get_agent("alex")
        jordan_prof, jordan_map = agent_registry.get_agent("jordan")

        # Distinct pipeline IDs
        self.assertEqual(alex_map.pipeline_id, "eb714d82ec524f14981e5b5f5108cbd1")
        self.assertEqual(jordan_map.pipeline_id, "642bb4345fa244099a78a50cede2d7d3")
        self.assertNotEqual(alex_map.pipeline_id, jordan_map.pipeline_id)

        # Distinct TTS voices
        self.assertEqual(alex_map.tts_voice, "echo")
        self.assertEqual(jordan_map.tts_voice, "nova")
        self.assertNotEqual(alex_map.tts_voice, jordan_map.tts_voice)

        # Distinct persona roles and instructions
        self.assertEqual(alex_prof.role, "Technical Manager")
        self.assertEqual(jordan_prof.role, "Senior Product Manager")
        self.assertNotEqual(alex_prof.instructions, jordan_prof.instructions)

        # Distinct focal competencies
        self.assertIn("system_design", alex_prof.focal_competencies)
        self.assertNotIn("system_design", jordan_prof.focal_competencies)
        self.assertIn("product_sense", jordan_prof.focal_competencies)
        self.assertNotIn("product_sense", alex_prof.focal_competencies)

        # Shared Custom LLM endpoint
        self.assertEqual(alex_map.llm_url, jordan_map.llm_url)
        self.assertEqual(alex_map.llm_vendor, jordan_map.llm_vendor)
        self.assertEqual(alex_map.llm_model, jordan_map.llm_model)

    # ── TEST 13 — No Secret Values in Generated Agora Payloads ─────────────
    def test_13_no_secret_values_in_payloads(self) -> None:
        """Verify that generated properties and join payloads do not contain API keys, certificates, or tokens."""
        _, jordan_map = agent_registry.get_agent("jordan")
        payload = jordan_map.to_agora_properties()

        # Check payload does not contain authorization headers, secrets, or keys
        self.assertNotIn("api_key", payload["llm"])
        self.assertNotIn("api_key", payload["asr"])
        self.assertNotIn("api_key", payload["tts"])
        self.assertNotIn("authorization", payload["llm"])
        self.assertNotIn("auth_jwt", payload)
        self.assertNotIn("certificate", payload)


if __name__ == "__main__":
    unittest.main()

