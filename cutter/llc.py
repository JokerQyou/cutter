import decimal
import os.path
import shlex
import typing

import ffmpeg
import json5
from loguru import logger

from cutter.trim import TrimVideo


class CutSegment(typing.TypedDict):
    start: decimal.Decimal
    end: decimal.Decimal
    name: str


def cut_llc_project(llc_project: str):
    with open(llc_project, 'r', encoding='utf8') as rf:
        project = json5.load(rf, parse_float=lambda v: decimal.Decimal(v))

    assert project.get('version') == 1
    input_media_file = os.path.join(os.path.dirname(llc_project), project['mediaFileName'])
    input_duration = decimal.Decimal(
        ffmpeg.probe(input_media_file, show_entries="format=duration")['streams'][0]['duration'],
    )
    logger.debug('Parsed LLC project. input="{}"', input_media_file, input_duration)

    # Reading key frames
    logger.debug('Reading input media file...')
    video = TrimVideo(input_media_file)
    logger.debug('Got {} key frames, total duration={}', len(video.key_frame_timestamps), video.duration)
    output_dir = os.path.join(os.path.dirname(llc_project), 'cuts')
    os.makedirs(output_dir, exist_ok=True)
    logger.debug('Cuts will be stored in "{}"', output_dir)

    seg: CutSegment
    for i, seg in enumerate(project.get('cutSegments', [])):
        start = seg.get('start', decimal.Decimal('0'))
        end = seg.get('end', input_duration)
        if seg.get('name', '').strip() == '':
            logger.debug('Skipped unlabeled segment start={}, end={}', start, end)
            continue

        output_file = os.path.join(output_dir, f"{i:02d} {seg['name'].strip()}.mp4")
        logger.debug('Cutting segment start={}, end={}, filename="{}"', start, end, output_file)
        trim_files, fast_trims_cmd, slow_trims_cmd = video.generate_trim(start, end)
        if len(fast_trims_cmd) > 0:
            for fast_trim_cmd in fast_trims_cmd:
                logger.debug('Fast trim, command="{}"', shlex.join(fast_trim_cmd.compile()))
                fast_trim_cmd.run(overwrite_output=True)
        if len(slow_trims_cmd) > 0:
            logger.debug('Slow trim, command="{}"', shlex.join(ffmpeg.merge_outputs(*slow_trims_cmd).compile()))
            ffmpeg.merge_outputs(*slow_trims_cmd).run(overwrite_output=True)
        merge_cmd = video.generate_merge(trim_files, output_file)
        logger.debug('Merging parts, command="{}"', shlex.join(merge_cmd.compile()))
        merge_cmd.run(overwrite_output=True)

    video.clean_temp()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Lossless cut post-cutter')
    parser.add_argument('llc_file', type=str, help='path to Lossless cut project file')
    args = parser.parse_args()

    cut_llc_project(args.llc_file)
