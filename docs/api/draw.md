# Drawing on images

`from interactive_pipe import draw` — pure functions drawing detections,
keypoints, regions and labels on a copy of an image, keeping its dtype and
range. See [Figures, heatmaps & overlays](../guide/figures-and-overlays.md#drawing-on-images-interactive_pipedraw)
for the conventions (coordinates, colours, speed).

::: interactive_pipe.draw
    options:
      show_root_heading: false
      members:
        - points
        - boxes
        - lines
        - polygon
        - text
        - mask
        - to_rgb
        - DEFAULT_COLORS
