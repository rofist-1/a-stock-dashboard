# -*- coding: utf-8 -*-
import json
d = json.load(open('底部放量_20260624.json', encoding='utf-8'))
for s in d['stocks']:
    sd = s.get('score_detail', {})
    gongzhen = sd.get('板块共振', 0)
    print('%s 行业=%s 板块共振=%d sector_in_hot=%s' % (s['name'], s.get('sector',''), gongzhen, s.get('sector_in_hot')))
