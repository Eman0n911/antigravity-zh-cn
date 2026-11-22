#!/usr/bin/env python3
"""Build and manage a local Simplified Chinese overlay for Antigravity 2.34.0.

The original app.asar is read locally. No Google application binary is bundled.
"""

import argparse
import copy
import hashlib
import json
import os
import pathlib
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parent
APP = pathlib.Path('/Applications/Antigravity.app')
MARKER = '// Antigravity 2.0 Chinese Localization Engine'
VERSION = '2.34.0'
TARGETS = ('dist/preload.js', 'dist/ideInstall/wizardPreload.js')
MENU_MARKER = '// Antigravity zh-CN native menu labels'


def app_paths(app):
    resources = app / 'Contents' / 'Resources'
    return resources / 'app.asar', resources / 'app.asar.zhcn-original-2.34.0'


def entry(header, name):
    node = header
    for part in name.split('/'):
        node = node['files'][part]
    return node


def read_asar(path):
    raw = path.read_bytes()
    if len(raw) < 16:
        raise ValueError('ASAR 文件过短')
    one, outer, inner, length = struct.unpack_from('<IIII', raw)
    if one != 4 or outer != inner + 4 or inner != (length + 3) // 4 * 4 + 4:
        raise ValueError('ASAR 头部格式不符')
    base = 16 + (length + 3) // 4 * 4
    header = json.loads(raw[16:16 + length])
    return header, raw[base:]


def file_bytes(header, body, name):
    meta = entry(header, name)
    if meta.get('unpacked'):
        raise ValueError(f'{name} 位于外部解包目录')
    start = int(meta['offset'])
    end = start + meta['size']
    if end > len(body):
        raise ValueError(f'{name} 超出 ASAR 数据范围')
    return body[start:end]


def asar_version(header, body):
    return json.loads(file_bytes(header, body, 'package.json'))['version']


def injection():
    code = "process.stdout.write(require('./vendor/build-injection').DOM_TRANSLATOR_INJECTION)"
    result = subprocess.run(['node', '-e', code], cwd=ROOT, check=True, capture_output=True)
    payload = result.stdout.decode('utf-8')
    # This package only translates UI. The upstream drag workaround is unrelated.
    needle = '    setupSidebarProjectDragFix();'
    if payload.count(needle) != 1:
        raise ValueError('翻译引擎版本与预期不符')
    payload = payload.replace(needle, '')
    return payload.encode('utf-8')


def integrity(data, block_size):
    digest = lambda part: hashlib.sha256(part).hexdigest()
    return {'algorithm': 'SHA256', 'hash': digest(data), 'blockSize': block_size,
            'blocks': [digest(data[i:i + block_size]) for i in range(0, len(data), block_size)]}


def make_asar(header, body):
    packed = json.dumps(header, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    pad = (-len(packed)) % 4
    head = struct.pack('<IIII', 4, len(packed) + pad + 8,
                       len(packed) + pad + 4, len(packed)) + packed + b'\0' * pad
    return head + body


def build(source, output):
    header, body = read_asar(source)
    version = asar_version(header, body)
    if version != VERSION:
        raise ValueError(f'仅支持 Antigravity {VERSION}，当前为 {version}')
    original = file_bytes(header, body, TARGETS[0])
    if MARKER.encode() in original:
        raise ValueError('输入包已包含中文补丁，请使用原版备份重新构建')
    payload = injection()
    new_header = copy.deepcopy(header)
    added = bytearray()
    for name in TARGETS:
        old = file_bytes(header, body, name)
        updated = old + b'\n\n' + payload + b'\n'
        meta = entry(new_header, name)
        meta['offset'] = str(len(body) + len(added))
        meta['size'] = len(updated)
        if 'integrity' in meta:
            block_size = meta['integrity']['blockSize']
            meta['integrity'] = integrity(updated, block_size)
        added.extend(updated)
    menu_name = 'dist/menu.js'
    menu = file_bytes(header, body, menu_name)
    menu_anchor = b'    // Re-apply the menu so the change takes effect.\n    electron_1.Menu.setApplicationMenu(menu);'
    if menu.count(menu_anchor) != 1:
        raise ValueError('本机菜单代码与 2.34.0 预期不符')
    menu_patch = (
        b'    ' + MENU_MARKER.encode() + b'\n'
        b'    if ((0, utils_1.isMacOS)()) {\n'
        b'        const labels = { File: "\xe6\x96\x87\xe4\xbb\xb6", Edit: "\xe7\xbc\x96\xe8\xbe\x91", View: "\xe8\xa7\x86\xe5\x9b\xbe", Window: "\xe7\xaa\x97\xe5\x8f\xa3", Help: "\xe5\xb8\xae\xe5\x8a\xa9" };\n'
        b'        for (const item of menu.items) {\n'
        b'            if (labels[item.label]) item.label = labels[item.label];\n'
        b'        }\n'
        b'    }\n'
    )
    updated_menu = menu.replace(menu_anchor, menu_patch + menu_anchor)
    menu_meta = entry(new_header, menu_name)
    menu_meta['offset'] = str(len(body) + len(added))
    menu_meta['size'] = len(updated_menu)
    if 'integrity' in menu_meta:
        menu_meta['integrity'] = integrity(updated_menu, menu_meta['integrity']['blockSize'])
    added.extend(updated_menu)
    result = make_asar(new_header, body + added)
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix='.agy-zhcn-', delete=False) as tmp:
        tmp.write(result)
        staged = pathlib.Path(tmp.name)
    try:
        check_header, check_body = read_asar(staged)
        assert asar_version(check_header, check_body) == VERSION
        for name in TARGETS:
            assert MARKER.encode() in file_bytes(check_header, check_body, name)
        assert MENU_MARKER.encode() in file_bytes(check_header, check_body, menu_name)
        staged.replace(output)
    finally:
        staged.unlink(missing_ok=True)
    print(f'已构建：{output}（{len(result)} 字节）')


def app_version(app):
    with (app / 'Contents' / 'Info.plist').open('rb') as stream:
        return plistlib.load(stream)['CFBundleShortVersionString']


def status(app):
    current, backup = app_paths(app)
    if not current.exists():
        raise FileNotFoundError(current)
    header, body = read_asar(current)
    print(f'应用版本：{app_version(app)}；ASAR 版本：{asar_version(header, body)}')
    print('中文补丁：' + ('已安装' if MARKER.encode() in file_bytes(header, body, TARGETS[0]) else '未安装'))
    print('原版备份：' + (str(backup) if backup.exists() else '不存在'))


def ensure_not_running():
    # pgrep may be unavailable inside restricted environments. A failed probe is
    # treated as unknown and install stops.
    probe = subprocess.run(['pgrep', '-f', r'/Antigravity\.app/Contents/MacOS/Antigravity([[:space:]]|$)'],
                           capture_output=True, text=True)
    if probe.returncode == 0:
        raise RuntimeError('Antigravity 正在运行。请先在应用中保存工作并正常退出。')
    if probe.returncode != 1 or probe.stderr.strip():
        raise RuntimeError('无法确认 Antigravity 是否已退出；安装已停止')


def replace_archive(source, destination):
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.agy-zhcn-', delete=False) as tmp:
        staged = pathlib.Path(tmp.name)
    try:
        shutil.copy2(source, staged)
        os.replace(staged, destination)
    finally:
        staged.unlink(missing_ok=True)


def install(app):
    current, backup = app_paths(app)
    if app_version(app) != VERSION:
        raise ValueError(f'应用版本不是 {VERSION}')
    ensure_not_running()
    head, body = read_asar(current)
    if asar_version(head, body) != VERSION:
        raise ValueError('当前 ASAR 版本不匹配')
    if MARKER.encode() in file_bytes(head, body, TARGETS[0]):
        print('中文补丁已安装')
        return
    if backup.exists() and backup.read_bytes() != current.read_bytes():
        raise ValueError(f'既有备份与当前原版不同，请先检查：{backup}')
    with tempfile.TemporaryDirectory(prefix='agy-zhcn-') as directory:
        candidate = pathlib.Path(directory) / 'app.zh-cn.asar'
        before = current.read_bytes()
        build(current, candidate)
        if current.read_bytes() != before:
            raise RuntimeError('应用资源在构建期间发生变化，请重试')
        if not backup.exists():
            # The original inode stays reachable after the atomic replacement.
            os.link(current, backup)
        replace_archive(candidate, current)
    print('中文补丁已安装。原版备份：' + str(backup))


def restore(app):
    current, backup = app_paths(app)
    if app_version(app) != VERSION:
        raise ValueError(f'应用版本不是 {VERSION}，不能恢复旧版 ASAR')
    ensure_not_running()
    current_head, current_body = read_asar(current)
    if asar_version(current_head, current_body) != VERSION:
        raise ValueError('当前 ASAR 版本不匹配，不能恢复旧版 ASAR')
    if MARKER.encode() not in file_bytes(current_head, current_body, TARGETS[0]):
        print('当前 ASAR 未安装此中文补丁')
        return
    if not backup.exists():
        raise FileNotFoundError(f'原版备份不存在：{backup}')
    original_head, original_body = read_asar(backup)
    if asar_version(original_head, original_body) != VERSION or MARKER.encode() in file_bytes(original_head, original_body, TARGETS[0]):
        raise ValueError('备份校验失败')
    replace_archive(backup, current)
    print('已恢复原版 ASAR，原版备份仍可用于核对。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'status', 'install', 'restore'))
    parser.add_argument('--app', type=pathlib.Path, default=APP)
    parser.add_argument('--output', type=pathlib.Path, default=ROOT / 'app.zh-cn.asar')
    args = parser.parse_args()
    current, backup = app_paths(args.app)
    if args.action == 'build':
        if args.output.resolve() in (current.resolve(), backup.resolve()):
            parser.error('--output 不能指向应用 ASAR 或其备份')
        header, body = read_asar(current)
        if asar_version(header, body) != VERSION:
            raise ValueError(f'仅支持 Antigravity {VERSION}')
        patched = MARKER.encode() in file_bytes(header, body, TARGETS[0])
        source = backup if patched else current
        build(source, args.output)
    elif args.action == 'status':
        status(args.app)
    elif args.action == 'install':
        install(args.app)
    else:
        restore(args.app)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'失败：{exc}', file=sys.stderr)
        sys.exit(1)
