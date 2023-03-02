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
This module is responsible for the rasterization step:
- it contains all functions related to 3D representation on a 2D raster grid
TODO: refactor in several files and remove too-many-lines
"""
# pylint: disable=C0302

# Standard imports
import logging
from typing import List, Tuple, Union

# Third party imports
import numpy as np
import pandas

# cars-rasterize
import rasterize as crasterize  # pylint:disable=E0401
import xarray as xr

# CARS imports
from cars.core import constants as cst


def compute_xy_starts_and_sizes(
    resolution: float, cloud: pandas.DataFrame
) -> Tuple[float, float, int, int]:
    """
    Compute xstart, ystart, xsize and ysize
    of the rasterization grid from a set of points

    :param resolution: Resolution of rasterized cells,
        expressed in cloud CRS units
    :param cloud: set of points as returned
        by the create_combined_cloud function
    :return: a tuple (xstart, ystart, xsize, ysize)
    """
    worker_logger = logging.getLogger("distributed.worker")

    # Derive xstart
    xmin = np.nanmin(cloud[cst.X].values)
    xmax = np.nanmax(cloud[cst.X].values)
    worker_logger.debug("Points x coordinate range: [{},{}]".format(xmin, xmax))

    # Clamp to a regular grid
    x_start = np.floor(xmin / resolution) * resolution
    x_size = int(1 + np.floor((xmax - x_start) / resolution))

    # Derive ystart
    ymin = np.nanmin(cloud[cst.Y].values)
    ymax = np.nanmax(cloud[cst.Y].values)
    worker_logger.debug("Points y coordinate range: [{},{}]".format(ymin, ymax))

    # Clamp to a regular grid
    y_start = np.ceil(ymax / resolution) * resolution
    y_size = int(1 + np.floor((y_start - ymin) / resolution))

    return x_start, y_start, x_size, y_size


def simple_rasterization_dataset_wrapper(
    cloud: pandas.DataFrame,
    resolution: float,
    epsg: int,
    xstart: float = None,
    ystart: float = None,
    xsize: int = None,
    ysize: int = None,
    sigma: float = None,
    radius: int = 1,
    dsm_no_data: int = np.nan,
    color_no_data: int = np.nan,
    msk_no_data: int = 65535,
    list_computed_layers: List[str] = None,
) -> xr.Dataset:
    """
    Wrapper of simple_rasterization
    that has xarray.Dataset as inputs and outputs.

    :param cloud: cloud to rasterize
    :param resolution: Resolution of rasterized cells,
        expressed in cloud CRS units or None
    :param epsg: epsg code for the CRS of the final raster
    :param color_list: Additional list of images
        with bands to rasterize (same size as cloud_list), or None
    :param xstart: xstart of the rasterization grid
        (if None, will be estimated by the function)
    :param ystart: ystart of the rasterization grid
        (if None, will be estimated by the function)
    :param xsize: xsize of the rasterization grid
        (if None, will be estimated by the function)
    :param ysize: ysize of the rasterization grid
        (if None, will be estimated by the function)
    :param sigma: sigma for gaussian interpolation.
        (If None, set to resolution)
    :param radius: Radius for hole filling.
    :param dsm_no_data: no data value to use in the final raster
    :param color_no_data: no data value to use in the final colored raster
    :param msk_no_data: no data value to use in the final mask image
    :param list_computed_layers: list of computed output data
    :return: Rasterized cloud
    """

    # combined clouds
    roi = (
        resolution is not None
        and xstart is not None
        and ystart is not None
        and xsize is not None
        and ysize is not None
    )

    # compute roi from the combined clouds if it is not set
    if not roi:
        (
            xstart,
            ystart,
            xsize,
            ysize,
        ) = compute_xy_starts_and_sizes(resolution, cloud)

    # rasterize clouds
    raster = rasterize(
        cloud,
        resolution,
        epsg,
        x_start=xstart,
        y_start=ystart,
        x_size=xsize,
        y_size=ysize,
        sigma=sigma,
        radius=radius,
        hgt_no_data=dsm_no_data,
        color_no_data=color_no_data,
        msk_no_data=msk_no_data,
        list_computed_layers=list_computed_layers,
    )

    return raster


def compute_values_1d(
    x_start: float, y_start: float, x_size: int, y_size: int, resolution: float
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute the x and y values as 1d arrays

    :param x_start: x start of the rasterization grid
    :param y_start: y start of the rasterization grid
    :param x_size: x size of the rasterization grid
    :param y_size: y size of the rasterization grid
    :param resolution: Resolution of rasterized cells,
        in cloud CRS units or None.
    :return: a tuple composed of the x and y 1d arrays
    """
    x_values_1d = np.linspace(
        x_start + 0.5 * resolution,
        x_start + resolution * (x_size + 0.5),
        x_size,
        endpoint=False,
    )
    y_values_1d = np.linspace(
        y_start - 0.5 * resolution,
        y_start - resolution * (y_size + 0.5),
        y_size,
        endpoint=False,
    )

    return x_values_1d, y_values_1d


def compute_vector_raster_and_stats(
    cloud: pandas.DataFrame,
    data_valid: np.ndarray,  # pylint: disable=W0613
    x_start: float,
    y_start: float,
    x_size: int,
    y_size: int,
    resolution: float,
    sigma: float,
    radius: int,
    msk_no_data: int,  # pylint: disable=W0613
    worker_logger: logging.Logger,  # pylint: disable=W0613
    list_computed_layers: List[str] = None,
) -> Tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    Union[None, np.ndarray],
]:
    """
    Compute vectorized raster and its statistics.

    :param cloud: Combined cloud
        as returned by the create_combined_cloud function
    :param data_valid: mask of points
        which are not on the border of its original epipolar image.
        To compute a cell it has to have at least one data valid,
        for which case it is considered that no contributing
        points from other neighbor tiles are missing.
    :param x_start: x start of the rasterization grid
    :param y_start: y start of the rasterization grid
    :param x_size: x size of the rasterization grid
    :param y_size: y size of the rasterization grid
    :param resolution: Resolution of rasterized cells,
        expressed in cloud CRS units or None.
    :param sigma: Sigma for gaussian interpolation. If None, set to resolution
    :param radius: Radius for hole filling.
    :param msk_no_data: No data value to use for the rasterized mask
    :param worker_logger: Logger
    :param list_computed_layers: list of computed output data
    :return: a tuple with rasterization results and statistics.
    """

    points = cloud.loc[:, [cst.X, cst.Y]].values.T

    # perform rasterization with gaussian interpolation
    clr_bands = [
        band
        for band in cloud
        if str.find(band, cst.POINTS_CLOUD_CLR_KEY_ROOT) >= 0
    ]
    values_bands = [cst.Z]
    values_bands.extend(clr_bands)

    confidence_index = []
    if substring_in_list(cloud.columns, "confidence_from") and (
        (list_computed_layers is None)
        or substring_in_list(list_computed_layers, "confidence_from")
    ):
        for key in cloud.columns:
            for _, confidence_name in enumerate(cst.POINTS_CLOUD_CONFIDENCE):
                if key == confidence_name:
                    confidence_index.append(confidence_name)
                    values_bands.append(confidence_name)
    values = cloud.loc[:, values_bands].values.T
    valid = data_valid[np.newaxis, :]

    out, mean, stdev, nb_pts_in_disc, nb_pts_in_cell = crasterize.pc_to_dsm(
        points,
        values,
        valid,
        x_start,
        y_start,
        x_size,
        y_size,
        resolution,
        radius,
        sigma,
    )

    confidences_out = None
    if len(confidence_index) > 0:
        confidences = out[..., -len(confidence_index) :]
        out = out[..., : -len(confidence_index)]
        confidences = confidences.reshape((len(confidence_index), -1))
        confidences_out = {}
        for k, key in enumerate(confidence_index):
            confidences_out[key] = confidences[k]

    return (
        out,
        mean,
        stdev,
        nb_pts_in_disc,
        nb_pts_in_cell,
        None,
        confidences_out,
    )


def substring_in_list(src_list, substring):
    """
    Check if the list contains substring
    """
    res = list(filter(lambda x: substring in x, src_list))
    return len(res) > 0


def create_raster_dataset(
    raster: np.ndarray,
    x_start: float,
    y_start: float,
    x_size: int,
    y_size: int,
    resolution: float,
    hgt_no_data: int,
    color_no_data: int,
    epsg: int,
    mean: np.ndarray,
    stdev: np.ndarray,
    n_pts: np.ndarray,
    n_in_cell: np.ndarray,
    msk: np.ndarray = None,
    confidences: np.ndarray = None,
) -> xr.Dataset:
    """
    Create final raster xarray dataset

    :param raster: height and colors
    :param x_start: x start of the rasterization grid
    :param y_start: y start of the rasterization grid
    :param x_size: x size of the rasterization grid
    :param y_size: y size of the rasterization grid
    :param resolution: Resolution of rasterized cells,
        expressed in cloud CRS units or None.
    :param hgt_no_data: no data value to use for height
    :param color_no_data: no data value to use for color
    :param epsg: epsg code for the CRS of the final raster
    :param mean: mean of height and colors
    :param stdev: standard deviation of height and colors
    :param n_pts: number of points that are stricty in a cell
    :param n_in_cell: number of points which contribute to a cell
    :param msk: raster msk
    :param confidence_from_ambiguity: raster msk
    :return: the raster xarray dataset
    """
    raster_dims = (cst.Y, cst.X)
    n_layers = raster.shape[-1]
    x_values_1d, y_values_1d = compute_values_1d(
        x_start, y_start, x_size, y_size, resolution
    )
    raster_coords = {cst.X: x_values_1d, cst.Y: y_values_1d}
    hgt = np.nan_to_num(raster[..., 0], nan=hgt_no_data)
    raster_out = xr.Dataset(
        {cst.RASTER_HGT: ([cst.Y, cst.X], hgt)}, coords=raster_coords
    )

    if raster.shape[-1] > 1:  # rasterizer produced color output
        band = range(1, raster.shape[-1])
        # CAUTION: band/channel is set as the first dimension.
        clr = np.nan_to_num(np.rollaxis(raster[:, :, 1:], 2), nan=color_no_data)
        color_out = xr.Dataset(
            {cst.RASTER_COLOR_IMG: ([cst.BAND, cst.Y, cst.X], clr)},
            coords={**raster_coords, cst.BAND: band},
        )
        # update raster output with color data
        raster_out = xr.merge((raster_out, color_out))

    raster_out.attrs[cst.EPSG] = epsg
    raster_out.attrs[cst.RESOLUTION] = resolution

    # statistics layer for height output
    raster_out[cst.RASTER_HGT_MEAN] = xr.DataArray(
        mean[..., 0], coords=raster_coords, dims=raster_dims
    )
    raster_out[cst.RASTER_HGT_STD_DEV] = xr.DataArray(
        stdev[..., 0], coords=raster_coords, dims=raster_dims
    )

    # add each band statistics
    for i_layer in range(1, n_layers):
        raster_out["{}{}".format(cst.RASTER_BAND_MEAN, i_layer)] = xr.DataArray(
            mean[..., i_layer], coords=raster_coords, dims=raster_dims
        )
        raster_out[
            "{}{}".format(cst.RASTER_BAND_STD_DEV, i_layer)
        ] = xr.DataArray(
            stdev[..., i_layer], coords=raster_coords, dims=raster_dims
        )

    raster_out[cst.RASTER_NB_PTS] = xr.DataArray(n_pts, dims=raster_dims)
    raster_out[cst.RASTER_NB_PTS_IN_CELL] = xr.DataArray(
        n_in_cell, dims=raster_dims
    )

    if msk is not None:
        raster_out[cst.RASTER_MSK] = xr.DataArray(msk, dims=raster_dims)
    if confidences is not None:
        for key in confidences:
            raster_out[key] = xr.DataArray(confidences[key], dims=raster_dims)
    return raster_out


def rasterize(
    cloud: pandas.DataFrame,
    resolution: float,
    epsg: int,
    x_start: float,
    y_start: float,
    x_size: int,
    y_size: int,
    sigma: float = None,
    radius: int = 1,
    hgt_no_data: int = -32768,
    color_no_data: int = 0,
    msk_no_data: int = 65535,
    list_computed_layers: List[str] = None,
) -> Union[xr.Dataset, None]:
    """
    Rasterize a point cloud with its color bands to a Dataset
    that also contains quality statistics.

    :param cloud: Combined cloud
        as returned by the create_combined_cloud function
    :param resolution: Resolution of rasterized cells,
        expressed in cloud CRS units or None.
    :param epsg: epsg code for the CRS of the final raster
    :param x_start: x start of the rasterization grid
    :param y_start: y start of the rasterization grid
    :param x_size: x size of the rasterization grid
    :param y_size: y size of the rasterization grid
    :param sigma: sigma for gaussian interpolation. If None, set to resolution
    :param radius: Radius for hole filling.
    :param hgt_no_data: no data value to use for height
    :param color_no_data: no data value to use for color
    :param msk_no_data: no data value to use in the final mask image
    :param list_computed_layers: list of computed output data
    :return: Rasterized cloud color and statistics.
    """
    worker_logger = logging.getLogger("distributed.worker")

    if sigma is None:
        sigma = resolution

    # generate validity mask from margins and all masks of cloud data.
    data_valid = cloud[cst.POINTS_CLOUD_VALID_DATA].values

    # If no valid points are found in cloud, return default values
    if np.size(data_valid) == 0:
        worker_logger.debug("No points to rasterize, returning None")
        return None

    worker_logger.debug(
        "Rasterization grid: start=[{},{}], size=[{},{}], resolution={}".format(
            x_start, y_start, x_size, y_size, resolution
        )
    )

    (
        out,
        mean,
        stdev,
        n_pts,
        n_in_cell,
        msk,
        confidences,
    ) = compute_vector_raster_and_stats(
        cloud,
        data_valid,
        x_start,
        y_start,
        x_size,
        y_size,
        resolution,
        sigma,
        radius,
        msk_no_data,
        worker_logger,
        list_computed_layers,
    )

    # reshape data as a 2d grid.
    shape_out = (y_size, x_size)
    out = out.reshape(shape_out + (-1,))
    mean = mean.reshape(shape_out + (-1,))
    stdev = stdev.reshape(shape_out + (-1,))
    n_pts = n_pts.reshape(shape_out)
    n_in_cell = n_in_cell.reshape(shape_out)

    if msk is not None:
        msk = msk.reshape(shape_out)
    if confidences is not None:
        for key in confidences:
            confidences[key] = confidences[key].reshape(shape_out)

    # build output dataset
    raster_out = create_raster_dataset(
        out,
        x_start,
        y_start,
        x_size,
        y_size,
        resolution,
        hgt_no_data,
        color_no_data,
        epsg,
        mean,
        stdev,
        n_pts,
        n_in_cell,
        msk,
        confidences,
    )

    return raster_out
