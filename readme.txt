1. Create a new conda environment (just to be on the safe-side)
2. git clone https://github.com/vkotaru/spinningup.git
    - cd spinningup
    - install the package by running
        `pip install -e .`
3. Go to gym-cassie folder, 
    - install the package in the similar manner
        `pip install -e .`


Run the following line to train the model

python -m spinup.run sac --hid "[256,256,256]" --epochs 50 --env Cassie-v1 --exp_name cassie_v1_sac_50_h3
