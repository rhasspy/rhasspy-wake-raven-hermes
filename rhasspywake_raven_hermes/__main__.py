"""Hermes MQTT service for Rhasspy wakeword with Raven"""
import argparse
import asyncio
import logging
import typing
from pathlib import Path

import paho.mqtt.client as mqtt
import rhasspyhermes.cli as hermes_cli
from rhasspysilence import WebRtcVadRecorder
from rhasspysilence.const import SilenceMethod
from rhasspywake_raven import Raven, Template

from . import WakeHermesMqtt

_DIR = Path(__file__).parent
_LOGGER = logging.getLogger("rhasspywake_raven_hermes")

# -----------------------------------------------------------------------------


def main():
    """Main method."""
    parser = argparse.ArgumentParser(prog="rhasspy-wake-raven-hermes")
    parser.add_argument(
        "--template-dir",
        help="Directory with Raven WAV templates (default: templates in Python module)",
    )
    parser.add_argument(
        "--probability-threshold",
        type=float,
        default=0.5,
        help="Probability above which detection occurs (default: 0.5)",
    )
    parser.add_argument(
        "--distance-threshold",
        type=float,
        default=0.22,
        help="Normalized dynamic time warping distance threshold for template matching (default: 0.22)",
    )
    parser.add_argument(
        "--minimum-matches",
        type=int,
        default=1,
        help="Number of templates that must match to produce output (default: 1)",
    )
    parser.add_argument(
        "--refractory-seconds",
        type=float,
        default=2.0,
        help="Seconds before wake word can be activated again (default: 2)",
    )
    parser.add_argument(
        "--window-shift-seconds",
        type=float,
        default=Raven.DEFAULT_SHIFT_SECONDS,
        help=f"Seconds to shift sliding time window on audio buffer (default: {Raven.DEFAULT_SHIFT_SECONDS})",
    )
    parser.add_argument(
        "--dtw-window-size",
        type=int,
        default=5,
        help="Size of band around slanted diagonal during dynamic time warping calculation (default: 5)",
    )
    parser.add_argument(
        "--vad-sensitivity",
        type=int,
        choices=[1, 2, 3],
        default=3,
        help="Webrtcvad VAD sensitivity (1-3)",
    )
    parser.add_argument(
        "--current-threshold",
        type=float,
        help="Debiased energy threshold of current audio frame",
    )
    parser.add_argument(
        "--max-energy",
        type=float,
        help="Fixed maximum energy for ratio calculation (default: observed)",
    )
    parser.add_argument(
        "--max-current-ratio-threshold",
        type=float,
        help="Threshold of ratio between max energy and current audio frame",
    )
    parser.add_argument(
        "--silence-method",
        choices=[e.value for e in SilenceMethod],
        default=SilenceMethod.VAD_ONLY,
        help="Method for detecting silence",
    )
    parser.add_argument(
        "--average-templates",
        action="store_true",
        help="Average wakeword templates together to reduce number of calculations",
    )
    parser.add_argument(
        "--wakeword-id",
        default="",
        help="Wakeword ID for model (default: use file name)",
    )
    parser.add_argument(
        "--udp-audio",
        nargs=3,
        action="append",
        help="Host/port/siteId for UDP audio input",
    )
    parser.add_argument(
        "--examples-dir", help="Save positive example audio to directory as WAV files"
    )
    parser.add_argument(
        "--examples-format",
        default="%Y%m%d-%H%M%S.wav",
        help="Format of positive example WAV file names using strftime (relative to examples-dir)",
    )
    parser.add_argument(
        "--log-predictions",
        action="store_true",
        help="Log prediction probabilities for each audio chunk (very verbose)",
    )

    hermes_cli.add_hermes_args(parser)
    args = parser.parse_args()

    hermes_cli.setup_logging(args)
    _LOGGER.debug(args)
    hermes: typing.Optional[WakeHermesMqtt] = None

    # -------------------------------------------------------------------------

    if args.examples_dir:
        args.examples_dir = Path(args.examples_dir)
        args.examples_dir.mkdir(parents=True, exist_ok=True)

    wav_paths: typing.List[Path] = []
    if args.template_dir:
        args.template_dir = Path(args.template_dir)

        if args.template_dir.is_dir():
            _LOGGER.debug("Loading WAV templates from %s", args.template_dir)
            wav_paths = list(args.template_dir.glob("*.wav"))

            if not wav_paths:
                _LOGGER.warning("No WAV templates found!")

    if not wav_paths:
        args.template_dir = _DIR / "templates"
        _LOGGER.debug("Loading WAV templates from %s", args.template_dir)
        wav_paths = list(args.template_dir.glob("*.wav"))

    # Create silence detector
    recorder = WebRtcVadRecorder(
        vad_mode=args.vad_sensitivity,
        silence_method=args.silence_method,
        current_energy_threshold=args.current_threshold,
        max_energy=args.max_energy,
        max_current_ratio_threshold=args.max_current_ratio_threshold,
    )

    # Load audio templates
    templates = [Raven.wav_to_template(p, name=p.name) for p in wav_paths]
    if args.average_templates:
        _LOGGER.debug("Averaging %s templates", len(templates))
        templates = [Template.average_templates(templates)]

    raven = Raven(
        templates=templates,
        recorder=recorder,
        probability_threshold=args.probability_threshold,
        minimum_matches=args.minimum_matches,
        distance_threshold=args.distance_threshold,
        refractory_sec=args.refractory_seconds,
        shift_sec=args.window_shift_seconds,
        debug=args.log_predictions,
    )

    udp_audio = []
    if args.udp_audio:
        udp_audio = [
            (host, int(port), site_id) for host, port, site_id in args.udp_audio
        ]

    # Listen for messages
    client = mqtt.Client()
    hermes = WakeHermesMqtt(
        client,
        raven=raven,
        minimum_matches=args.minimum_matches,
        examples_dir=args.examples_dir,
        examples_format=args.examples_format,
        wakeword_id=args.wakeword_id,
        udp_audio=udp_audio,
        site_ids=args.site_id,
    )

    _LOGGER.debug("Connecting to %s:%s", args.host, args.port)
    hermes_cli.connect(client, args)
    client.loop_start()

    try:
        # Run event loop
        asyncio.run(hermes.handle_messages_async())
    except KeyboardInterrupt:
        pass
    finally:
        _LOGGER.debug("Shutting down")
        client.loop_stop()


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
