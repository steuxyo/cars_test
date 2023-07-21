#!/usr/bin/env python
# coding: utf8
#
# Copyright (c) 2020 Centre National d'Etudes Spatiales (CNES).
#
# This file is part of CARS
# (see https://github.com/CNES/cars).
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""
cars-starter: helper to create configuration file
"""

# pylint: disable=import-outside-toplevel
# standard imports
import argparse
import json
import os


def inputfilename_to_sensor(inputfilename):
    """
    Fill sensor dictionary according to an input filename
    """
    sensor = {}

    absfilename = os.path.abspath(inputfilename)
    dirname = os.path.dirname(absfilename)
    basename = os.path.basename(absfilename)

    if basename.startswith("DIM") and basename.endswith("XML"):
        geomodel = os.path.join(dirname, "RPC" + basename[3:])
        if os.path.exists(geomodel) is False:
            raise FileNotFoundError(geomodel + " does not exist")

    elif basename.endswith(".tif"):
        geomodel = os.path.splitext(absfilename)[0] + ".geom"
        if os.path.exists(geomodel) is False:
            raise FileNotFoundError(geomodel + " does not exist")
    else:
        raise ValueError(absfilename + " not supported")

    sensor["image"] = absfilename
    sensor["geomodel"] = geomodel
    sensor["no_data"] = 0

    return sensor


def main():
    """
    Main cars-starter entrypoint
    """
    parser = argparse.ArgumentParser(
        "cars-starter", description="Helper to create configuration file"
    )
    parser.add_argument(
        "-il",
        type=str,
        nargs="*",
        metavar="input.tif",
        help="Inputs list",
        required=True,
    )

    parser.add_argument(
        "-out",
        type=str,
        metavar="out_dir",
        help="Output directory",
        required=True,
    )

    parser.add_argument(
        "--full", action="store_true", help="Fill all default values"
    )

    parser.add_argument("--check", action="store_true", help="Check inputs")

    args = parser.parse_args()

    config = {"inputs": {"sensors": {}}, "output": {}}
    pipeline_name = "sensors_to_dense_dsm"

    for idx, inputfilename in enumerate(args.il):
        config["inputs"]["sensors"][str(idx)] = inputfilename_to_sensor(
            inputfilename
        )

    # pairing with first image as reference
    pairing = list(
        zip(  # noqa: B905
            ["0"] * (len(args.il) - 1), map(str, range(1, len(args.il)))
        )
    )

    config["inputs"]["pairing"] = pairing
    config["output"]["out_dir"] = args.out

    if args.check or args.full:
        # cars imports
        from cars.pipelines.pipeline import Pipeline

        used_pipeline = Pipeline(pipeline_name, config, None)
        if args.full:
            config = used_pipeline.used_conf

    print(json.dumps(config, indent=4))


if __name__ == "__main__":
    main()
