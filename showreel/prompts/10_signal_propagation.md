Build an interactive demo with interactive_pipe, using PyTorch, of signal propagation at initialization in a deep MLP (around 50 layers): push a batch of random inputs through the freshly initialized network and plot, layer by layer, the standard deviation of the activations and of the gradients. Controls for the activation function, the initialization scheme and its gain, and whether normalization layers are used. Students should see activations vanish or explode with a bad gain, and why He and Xavier initialization and normalization exist.

Line budget: 70. PyTorch allowed.
