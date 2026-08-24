"""Tests for stable segmentation of streamed canonical assistant text."""

from __future__ import annotations

import unittest

from project_akiha.services.response_segmenter import StableResponseSegmenter


class StableResponseSegmenterTest(unittest.TestCase):
    def test_streams_completed_english_sentences_in_order(self) -> None:
        segmenter = StableResponseSegmenter("response-1")

        self.assertEqual(segmenter.push("Hello there."), ())
        first = segmenter.push(" How are you? I am well")
        final = segmenter.finish()

        self.assertEqual(
            [segment.canonical_text for segment in (*first, *final)],
            ["Hello there.", "How are you?", "I am well"],
        )
        self.assertEqual(
            [segment.segment_index for segment in (*first, *final)],
            [0, 1, 2],
        )
        self.assertEqual(
            [segment.is_final for segment in (*first, *final)],
            [False, False, True],
        )

    def test_recognizes_japanese_boundaries_without_spaces(self) -> None:
        segmenter = StableResponseSegmenter("response-2")

        segments = segmenter.push(
            "\u627f\u77e5\u3057\u307e\u3057\u305f\u3002\u3059\u3050\u306b\u78ba\u8a8d\u3057\u307e\u3059\uff01\u5c11\u3005\u304a\u5f85\u3061\u304f\u3060\u3055\u3044\u3002"
        )
        final = segmenter.finish()

        self.assertEqual(
            [segment.canonical_text for segment in (*segments, *final)],
            [
                "\u627f\u77e5\u3057\u307e\u3057\u305f\u3002",
                "\u3059\u3050\u306b\u78ba\u8a8d\u3057\u307e\u3059\uff01",
                "\u5c11\u3005\u304a\u5f85\u3061\u304f\u3060\u3055\u3044\u3002",
            ],
        )
        self.assertTrue(final[0].is_final)

    def test_batches_short_sentences_for_continuous_local_speech(self) -> None:
        segmenter = StableResponseSegmenter(
            "response-batched",
            minimum_streaming_chars=96,
        )
        text = (
            "\u4eca\u65e5\u3082\u7a4f\u3084\u304b\u306b\u904e\u3054\u3057\u3066\u304a\u308a\u307e\u3059\u3002\n\n"
            "\u4f55\u304b\u624b\u4f1d\u3048\u308b\u3053\u3068\u304c\u3042\u308c\u3070\u3001"
            "\u9060\u616e\u306a\u304f\u4ef0\u3063\u3066\u304f\u3060\u3055\u3044\u3002"
        )

        self.assertEqual(segmenter.push(text), ())
        final = segmenter.finish()

        self.assertEqual(len(final), 1)
        self.assertEqual(final[0].canonical_text, text)
        self.assertTrue(final[0].is_final)

    def test_releases_batched_sentences_once_streaming_target_is_met(self) -> None:
        segmenter = StableResponseSegmenter(
            "response-batched-long",
            minimum_streaming_chars=32,
            minimum_clause_chars=32,
        )

        segments = segmenter.push(
            "First short sentence. Second sentence creates runway. Tail begins"
        )

        self.assertEqual(len(segments), 1)
        self.assertEqual(
            segments[0].canonical_text,
            "First short sentence. Second sentence creates runway.",
        )

    def test_waits_for_sentence_boundary_split_across_chunks(self) -> None:
        segmenter = StableResponseSegmenter("response-3")

        self.assertEqual(segmenter.push("This is still incom"), ())
        self.assertEqual(segmenter.push("plete."), ())
        segments = segmenter.push(" The next sentence begins")

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].canonical_text, "This is still incomplete.")

    def test_does_not_split_decimal_abbreviation_or_numbered_list_marker(self) -> None:
        segmenter = StableResponseSegmenter("response-4")
        text = "Use version 3.14, e.g. the stable build. 1. Keep it installed. Done."

        segments = segmenter.push(text)
        final = segmenter.finish()

        self.assertEqual(
            [segment.canonical_text for segment in (*segments, *final)],
            [
                "Use version 3.14, e.g. the stable build.",
                "1. Keep it installed.",
                "Done.",
            ],
        )

    def test_releases_only_long_conservative_clauses(self) -> None:
        segmenter = StableResponseSegmenter(
            "response-5",
            minimum_clause_chars=40,
            clause_release_chars=12,
            maximum_segment_chars=100,
        )
        prefix = "This deliberately long response remains one stable clause"

        segments = segmenter.push(f"{prefix}, and generation continues afterward")

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].canonical_text, f"{prefix},")
        self.assertFalse(segments[0].is_final)

    def test_bounds_unpunctuated_text_at_a_word_boundary(self) -> None:
        segmenter = StableResponseSegmenter(
            "response-6",
            minimum_clause_chars=32,
            clause_release_chars=8,
            maximum_segment_chars=40,
        )

        segments = segmenter.push("word " * 11)

        self.assertEqual(len(segments), 1)
        self.assertLessEqual(len(segments[0].canonical_text), 40)
        self.assertTrue(segments[0].canonical_text.endswith("word"))

    def test_cancel_discards_unstable_tail_and_rejects_late_deltas(self) -> None:
        segmenter = StableResponseSegmenter("response-7")
        segmenter.push("Never expose this unfinished response")

        segmenter.cancel()

        self.assertEqual(segmenter.pending_text_length, 0)
        self.assertEqual(segmenter.finish(), ())
        with self.assertRaisesRegex(RuntimeError, "finished"):
            segmenter.push("late provider text")

    def test_finish_is_idempotent(self) -> None:
        segmenter = StableResponseSegmenter("response-8")
        segmenter.push("One final response.")

        first = segmenter.finish()

        self.assertEqual(len(first), 1)
        self.assertTrue(first[0].is_final)
        self.assertEqual(segmenter.finish(), ())


if __name__ == "__main__":
    unittest.main()
