# Traveler character model asset

Put the downloaded Sketchfab archive or the extracted .blend file in this folder.

Supported input:
- *.zip containing one or more .blend files
- *.blend

The project runner will:
1. extract ZIP files when needed;
2. append the real humanoid geometry;
3. preserve imported hierarchy/armature;
4. normalize the model to human scale;
5. create controlled lighting/camera;
6. save traveler_character.blend and traveler_preview.png.
