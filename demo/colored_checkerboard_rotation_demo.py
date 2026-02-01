"""
Demo showcasing affine transformations and color rotation matrices.

This demo demonstrates:
- Colored checkerboard generation
- Affine transformations (rotation + translation) with 2x3 matrix display
- HSV-based color rotation with 3x3 RGB rotation matrix display
- Headerless tables for mathematical matrix visualization
"""

import argparse

import cv2
import numpy as np

from interactive_pipe import (
    CircularControl,
    Control,
    Panel,
    interactive,
    interactive_pipeline,
    layout,
)
from interactive_pipe.data_objects.table import Table


def create_checkerboard(checker_size: int = 64, board_size: int = 512):
    """Create a colored checkerboard image."""
    img = np.zeros((board_size, board_size, 3), dtype=np.float32)

    # Create coordinate grids
    y, x = np.ogrid[:board_size, :board_size]

    # Create checkerboard pattern
    checker_x = (x // checker_size) % 2
    checker_y = (y // checker_size) % 2
    checker = (checker_x + checker_y) % 2

    # Use vibrant colors: red/cyan and blue/yellow pairs
    # Red squares
    img[checker == 0, 0] = 1.0  # Red channel
    img[checker == 0, 1] = 0.0  # Green channel
    img[checker == 0, 2] = 0.0  # Blue channel

    # Cyan squares
    img[checker == 1, 0] = 0.0  # Red channel
    img[checker == 1, 1] = 1.0  # Green channel
    img[checker == 1, 2] = 1.0  # Blue channel

    return img


def apply_affine_transform(
    img: np.ndarray,
    rotation: float = 0.0,
    translate_x: float = 0.0,
    translate_y: float = 0.0,
):
    """Apply affine transformation (rotation + translation) to image.

    Returns:
        tuple: (transformed_image, 2x3_affine_matrix)
    """
    h, w = img.shape[:2]
    center_x, center_y = w / 2.0, h / 2.0

    # Convert rotation to radians
    angle_rad = np.radians(rotation)
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)

    # Build the 2x3 affine transformation matrix for display
    # This represents: rotation + translation in homogeneous coordinates
    # [[cos, -sin, tx], [sin, cos, ty]]
    affine_matrix = np.array(
        [
            [cos_a, -sin_a, translate_x],
            [sin_a, cos_a, translate_y],
        ],
        dtype=np.float32,
    )

    # For cv2.warpAffine, we need rotation around center, then translation
    # Get rotation matrix around center
    M_rot = cv2.getRotationMatrix2D((center_x, center_y), rotation, 1.0)

    # Add translation to the rotation matrix
    M = M_rot.copy()
    M[0, 2] += translate_x
    M[1, 2] += translate_y

    # Convert image to uint8 for cv2
    img_uint8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)

    # Apply affine transformation
    transformed = cv2.warpAffine(img_uint8, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

    # Convert back to float [0, 1]
    transformed = transformed.astype(np.float32) / 255.0

    # Return transformed image and the 2x3 matrix for display
    return transformed, affine_matrix


def format_affine_matrix(img: np.ndarray, matrix: np.ndarray):
    """Format the affine matrix as a headerless table."""
    # Create headerless table from 2x3 matrix
    affine_table = Table(matrix, title="Affine Matrix (2x3)", precision=4)
    layout.set_style("affine", title="Affine Transformation Matrix")

    return img, affine_table


def apply_color_rotation(
    img: np.ndarray,
    hue: float = 0.0,
    saturation: float = 1.0,
    value: float = 1.0,
):
    """Apply color rotation matrix to image and return both transformed image and matrix table.

    This applies a 3x3 RGB rotation matrix for HSV hue rotation.
    """
    # Convert hue to radians
    hue_rad = np.radians(hue)
    cos_h = np.cos(hue_rad)
    sin_h = np.sin(hue_rad)

    # Compute matrix coefficients using Rodrigues rotation formula
    # Rotation around (1,1,1)/sqrt(3) axis in RGB space
    # a = diagonal term, b = off-diagonal base, d = rotation component
    a = (1.0 + 2.0 * cos_h) / 3.0  # Diagonal
    b = (1.0 - cos_h) / 3.0  # Off-diagonal base
    d = sin_h / np.sqrt(3.0)  # Rotation component

    # Build 3x3 RGB hue rotation matrix
    # At hue=0: identity matrix
    # At hue=120°: R→G→B→R rotation
    hue_matrix = np.array(
        [[a, b - d, b + d], [b + d, a, b - d], [b - d, b + d, a]],
        dtype=np.float32,
    )

    # Build saturation matrix
    # Saturation blends between grayscale (s=0) and original color (s=1)
    # Using Rec.709 luminance weights
    Lr, Lg, Lb = 0.2126, 0.7152, 0.0722
    s = saturation
    sat_matrix = np.array(
        [
            [(1 - s) * Lr + s, (1 - s) * Lg, (1 - s) * Lb],
            [(1 - s) * Lr, (1 - s) * Lg + s, (1 - s) * Lb],
            [(1 - s) * Lr, (1 - s) * Lg, (1 - s) * Lb + s],
        ],
        dtype=np.float32,
    )

    # Combine: first hue rotation, then saturation, then value (brightness)
    # Combined matrix = value * (sat_matrix @ hue_matrix)
    scaled_matrix = value * (sat_matrix @ hue_matrix)

    # Apply color matrix to image
    # Reshape image to (height*width, 3) for matrix multiplication
    h, w = img.shape[:2]
    img_flat = img.reshape(-1, 3)
    # Apply matrix transformation: each RGB pixel = matrix @ pixel
    transformed_flat = img_flat @ scaled_matrix.T
    # Reshape back to original shape
    transformed_img = transformed_flat.reshape(h, w, 3)
    # Clip to valid range
    transformed_img = np.clip(transformed_img, 0.0, 1.0)

    # Create headerless table for display
    color_table = Table(
        scaled_matrix,
        title=f"RGB Matrix \nH={hue:.1f}°\nS={saturation:.2f}\nV={value:.2f}",
        precision=4,
    )
    layout.set_style("color_matrix", title="Color Rotation Matrix")

    return transformed_img, color_table


def affine_color_pipeline():
    """Main pipeline function."""
    # Create checkerboard
    checkerboard = create_checkerboard()

    # Apply affine transformation
    transformed_img, affine_matrix = apply_affine_transform(checkerboard)

    # Format affine matrix as table
    final_img, affine_table = format_affine_matrix(transformed_img, affine_matrix)

    # Apply color rotation to image and get matrix table
    colorized_img, color_table = apply_color_rotation(final_img)

    # Return: [image, affine_matrix_table, color_matrix_table]
    return [[colorized_img, affine_table, color_table]]


def add_interactivity():
    """Set up panels and controls for the demo."""
    # Create panels for grouping controls
    checkerboard_panel = Panel("Checkerboard", collapsible=True, collapsed=True)
    affine_panel = Panel("Affine Transform", collapsible=True, collapsed=False)
    color_panel = Panel("Color", collapsible=True, collapsed=False, position="right")

    # Checkerboard controls
    interactive(
        checker_size=Control(
            64,
            [16, 128],
            name="Checker Size",
            group=checkerboard_panel,
            tooltip="Size of each checker square in pixels",
        ),
        board_size=Control(
            512,
            [256, 1024],
            name="Board Size",
            group=checkerboard_panel,
            tooltip="Overall size of the checkerboard image",
        ),
    )(create_checkerboard)

    # Affine transform controls - use CircularControl for rotation
    interactive(
        rotation=CircularControl(
            0.0,
            [0.0, 360.0],
            name="Rotation",
            group=affine_panel,
            tooltip="Rotation angle in degrees (0-360°)",
        ),
        translate_x=Control(
            0.0,
            [-100.0, 100.0],
            name="Translate X",
            group=affine_panel,
            tooltip="Horizontal translation in pixels",
        ),
        translate_y=Control(
            0.0,
            [-100.0, 100.0],
            name="Translate Y",
            group=affine_panel,
            tooltip="Vertical translation in pixels",
        ),
    )(apply_affine_transform)

    # Format affine matrix (no controls)
    interactive()(format_affine_matrix)

    # Color controls - use CircularControl for hue
    interactive(
        hue=CircularControl(
            0.0,
            [0.0, 360.0],
            name="Hue",
            group=color_panel,
            tooltip="Hue rotation in degrees (0-360°). 120° shifts R→G→B→R",
        ),
        saturation=Control(
            1.0,
            [0.0, 2.0],
            name="Saturation",
            group=color_panel,
            tooltip="Color saturation. 0=grayscale, 1=original, >1=vibrant",
        ),
        value=Control(
            1.0,
            [0.0, 2.0],
            name="Value",
            group=color_panel,
            tooltip="Brightness multiplier. 0=black, 1=original, >1=brighter",
        ),
    )(apply_color_rotation)


def launch(backend="qt"):
    """Launch the demo with the specified backend."""
    add_interactivity()
    interactive_pipeline(gui=backend, cache=False, name="Affine & Color Demo")(affine_color_pipeline)()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Affine transformation and color rotation matrix demo")
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "gradio", "mpl", "nb"],
        default="qt",
        help="Backend to use: qt, gradio, mpl, or nb (default: qt)",
    )
    args = parser.parse_args()
    launch(backend=args.backend)
