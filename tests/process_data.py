import jsonlines
from typing import cast, Dict, List

def save_jsonl(datas: List[Dict]):
    with jsonlines.open('data_processed/IrishFinanceChatML.jsonl', mode='w') as writer:
        writer.write_all(datas)
    print('write successfully!')

def filter_system_item(data: Dict):
    return data.get('role') != 'system'

def main():
    max_items: int = 2000
    idx: int = 0
    total_message: List[Dict[str, str]] = list()
    with jsonlines.open('datas/IrishFinanceChatML.jsonl', mode='r') as reader:
        for obj in reader:
            obj = cast(Dict[str, List[Dict[str, str]]], obj)
            if len(obj) > 1: raise Exception(f'extract key in obj: {', '.join(list(obj.keys()))}')
            total_message.extend(list(filter(filter_system_item, obj.get('messages'))))
            if len(total_message) >= max_items: total_message = total_message[:max_items]; break
            idx += 1
    print(len(total_message))
    input('continue')
    # print(total_message)
    save_jsonl(total_message)


if __name__ == '__main__':
    main()