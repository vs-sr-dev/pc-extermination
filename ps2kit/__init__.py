"""ps2kit — game-agnostic building blocks for PS2 reverse engineering and ports.

Each module handles one thing the PS2 platform or its SDK imposes on every
game, independent of any particular title:

    elf         load an EE executable, map addresses, find lui/addiu xrefs
    adpcm       SPU (PS-ADPCM) decoding
    pss         Sony PSS movies: MPEG-2 video plus SShd/SSbd audio
    mwo3        CodeWarrior "MWo3" overlay modules
    fingerprint scan a disc tree and report what it recognises

Everything here is pure Python 3.8+ with no dependencies. Game-specific
knowledge belongs in the game's own tools/, not here.
"""
