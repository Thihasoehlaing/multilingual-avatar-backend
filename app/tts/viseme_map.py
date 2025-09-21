VISEME_MAP = {
    "p": "PP",       # p/b/m
    "t": "DD",       # t/d/n/l
    "S": "CH_SH_JH", # sh/ch/jh/zh
    "T": "TH",       # th
    "f": "FF",       # f/v
    "k": "KK",       # k/g
    "i": "EE",       # ee
    "r": "RR",       # r
    "s": "SS",       # s/z
    "u": "UW",       # oo
    "@": "AX",       # schwa
    "a": "AA",       # ah
    "e": "EH",       # eh
    "o": "AO",       # aw
    "O": "OW",       # oh
    "E": "EY",       # ay
    "U": "UH",       # uh
}

# Optional timing parameters frontend can use
VSM_TIMING = {
    "minFrameMs": 16,
    "clampLeadMs": 80,
    "clampTrailMs": 80,
    "blendIn": 0.06,
    "blendOut": 0.08,
}
