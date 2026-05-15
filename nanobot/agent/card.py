from typing import List, Dict, Tuple
from uuid import uuid4

def build_card(resource: List[str]) -> Tuple[Dict, str]:
    res = dict()
    res_string: str = ''
    res['schema'] = '2.0'
    res['config'] = {'streaming_mode': True, 'wide_screen_mode': True}
    
    # set header
    res['header'] = {
        'title': {'tag': 'plain_text', 'content': 'Nanobot'},
        'subtitle': {'tag': 'plain_text', 'content': '工作记忆助手'},
        'template': 'violet',
        'icon': {
            'tag': 'standard_icon',
            'token': 'robot_outlined',
            'color': 'orange',
        },
    }
    
    eles: List[Dict] = list()
    eles.append({'tag': 'markdown', 'element_id': uuid4().hex[:10], 'content': resource[0]})
    
    # add a collapsible_panel
    cp = {'tag': 'collapsible_panel', 'element_id': uuid4().hex[:10]}
    cp['header'] = {
        'title': {'tag': 'markdown', 'content': '**其他参考来源**'},
    }
    cp_eles: List[Dict] = list()
    for idx, r in enumerate(resource[1:]):
        if idx > 0: cp_eles.append({'tag': 'hr', 'element_id': uuid4().hex[:10], 'margin': '0px 0px 0px 0px'})
        cp_eles.append({'tag': 'markdown', 'element_id': uuid4().hex[:10], 'content': r})
    cp['elements'] = cp_eles
    eles.append(cp)

    res['body'] = {
        'elements': eles,
    }
    return res, res_string