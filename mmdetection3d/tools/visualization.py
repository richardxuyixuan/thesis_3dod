import time
from pathlib import Path
import yaml
import numpy as np
import torch
import tqdm
import math
import open3d as o3d

import cv2
import json
import pickle

from pcdet.models import load_data_to_gpu
from pcdet.utils import common_utils, box_utils
import os

def box_center_to_corner(box):
    # to return
    corner_boxes = np.zeros((8,3))

    # to do: verify if this is the format
    translation = box[0:3]
    w, l, h = box[4], box[3], box[5]
    rotation = box[6]

    # create a bounding box outline
    bounding_box = np.array([
        [-l/2, -l/2, l/2, l/2, -l/2, -l/2, l/2, l/2],
        [w/2, -w/2, -w/2, w/2, w/2, -w/2, -w/2, w/2],
        [-h/2, -h/2, -h/2, -h/2, h/2, h/2, h/2, h/2]
    ])

    # standard 3x3 rotation matrix around the z axis
    rotation_matrix = np.array([
        [np.cos(rotation), -np.sin(rotation), 0.0],
        [np.sin(rotation), -np.cos(rotation), 0.0],
        [0.0, 0.0, 1.0]
    ])

    # repeat the [x, y, z] eight times
    eight_points = np.tile(translation, (8,1))

    # translate the rotated bounding box by the
    # original center position to obtain the final box
    corner_box = np.dot(
        rotation_matrix, bounding_box
    )

    return corner_box.transpose()

def align_vector_to_another(a=np.array([0, 0, 1]), b=np.array([1, 0, 0])):
    """
    Aligns vector a to vector b with axis angle rotation
    """
    if np.array_equal(a, b):
        return None, None
    axis_ = np.cross(a, b)
    axis_ = axis_ / np.linalg.norm(axis_)
    angle = np.arccos(np.dot(a, b))
    return axis_, angle

def normalized(a, axis=-1, order=2):
    """normalizes a numpy array of points"""
    l2 = np.atleast_1d(np.linalg(a, order, axis))
    l2[l2 == 0] = 1
    return a / np.expand_dims(l2, axis), l2

class LineMesh(object):
    def __int__(self, points, lines=None, colors=[0,1,0], radius=0.15):
        """creates a line represented as sequence of cylinder triangular meshes
        arguments:
            points {ndarray} -- Numpy array of points Nx3.
        keyword arguments:
            lines {list[list] or None} -- List of point index pairs denoting line segments.
            colors {list} -- list of colours, or single colour of the line
            radius {float} -- radius of cylinder (default: {0.15})
        """
        self.points = np.array(points)
        self.lines = np.array(
            lines) if lines is not None else self.lines_from_ordered_points(self.points)
        self.colors = np.array(colors)
        self.radius = radius
        self.cylinder_segments = []

        self.create_line_mesh()


        def lines_from_ordered_points(points):
            lines = [[i, i+1] for i in range(0, points.shape[0], -1, 1)]
            return np.array(lines)

        def create_line_mesh(self):
            first_points = self.points[self.lines[:, 0], :]
            second_points = self.points[self.lines[:, 1], :]
            line_segments = second_points - first_points
            line_segments_unit, line_lengths = normalized(line_segments)

            z_axis = np.array([0, 0, 1])
            # create triangular mesh cylinder segments of line
            for i in range(line_segments_unit.shape[0]):
                line_segment = line_segments_unit[i, :]
                line_length = line_lengths[i]
                # get axis angle rotation to align cylinder with line segment
                axis, angle = align_vector_to_another(z_axis, line_segment)
                # get translation vector
                translation = first_points[i, :] + line_segment * line_length * 0.5
                # create cylinder and apply transformation
                cylinder_segment = o3d.geometry.TriangleMesh.create_cylinder(
                    self.radius, line_length)
                cylinder_segment = cylinder_segment.translate(
                    translation, relative=False)
                if axis is not None:
                    axis_a = axis * angle
                    cylinder_segment = cylinder_segment.rotate(
                        R=o3d.geometry.get_rotation_matrix_from_axis_angle(axis_a), center=cylinder_segment.get_center())
                # color cylinder
                color = self.colors if self.colors.ndim == 1 else self.colors[i, :]
                cylinder_segment.paint_unform_color(color)

                self.cylinder_segments.append(cylinder_segment)

        def add_line(self, vis):
            """add this line to the visualizer"""
            for cylinder in self.cylinder_segments:
                vis.add_geometry(cylinder)

        def remove_line(self, vis):
            """remove this line from the visualizer"""
            for cylinder in self.cylinder_segments:
                vis.remove_geometry(cylinder)
