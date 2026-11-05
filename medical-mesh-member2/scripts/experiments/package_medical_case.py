"""Create a compact course hand-in. Full sample arrays remain in experiment run."""
from pathlib import Path
import argparse
import json
import zipfile
import hashlib
ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',default='runs/medical_patella_verified_20261022')
    args=parser.parse_args();run=Path(args.out).resolve()
    delivery=ROOT.parent/'outputs'/'真实MRI髌骨模型_课设实验报告'
    dest=ROOT.parent/'outputs'/'真实MRI髌骨模型_课设提交包.zip'
    audit=json.loads((run/'artifact_verification.json').read_text())
    if not audit['all_passed']:raise ValueError('Cannot package a failed experiment as final')
    mapping={}
    def add(src,target):
        if Path(src).is_file():mapping[str(target)]=Path(src)
    for file in delivery.rglob('*'):
        if file.is_file():add(file,Path('报告')/file.relative_to(delivery))
    for file in run.rglob('*'):
        if not file.is_file():continue
        # Preserve geometry snapshots, exclude only large stochastic sample arrays.
        if file.suffix=='.npz' and ('samples' in file.stem or file.stem.startswith('stability_')):continue
        add(file,Path('experiment')/run.name/file.relative_to(run))
    for previous in ['medical_patella_20261022','medical_patella_initial_20261022']:
        directory=ROOT/'runs'/previous
        for file in directory.rglob('*.json'):
            if not file.name.endswith('.mesh.json'):add(file,Path('experiment')/previous/file.relative_to(directory))
    for folder in ['src','scripts/experiments','tests']:
        for file in (ROOT/folder).rglob('*.py'):
            add(file,Path('reproduction/work')/file.relative_to(ROOT))
    for name in ['pyproject.toml','requirements.in','requirements-lock-macos-arm64-py312.txt','README.md','THIRD_PARTY_NOTICES.md','run','启动医学网格工作台.command']:
        add(ROOT/name,Path('reproduction/work')/name)
    for file in (ROOT/'configs').glob('*.json'):
        if '.local.' not in file.name:add(file,Path('reproduction/work/configs')/file.name)
    for file in (ROOT/'docs').glob('*.md'):
        add(file,Path('reproduction/work/docs')/file.name)
    source=ROOT/'data/public/spl_knee/source'
    for name in ['Data/Model_98_patella.vtk','LICENSE.md','3D-Slicer-License.txt','MRI_header.txt','KneeAtlas-2015Sept-Slicer4-4Version.mrml','source_page.html','atlasStructure.json']:
        add(source/name,Path('source')/name)
    for src,name in [(run/'selected_candidate.stl','patella_2400.stl'),(run/'conversion/stl_to_step/converted.step','patella_2400.step'),(run/'conversion/stl_to_igs/converted.igs','patella_2400.igs')]:
        add(src,Path('model_samples')/name)
    readme='''# 课设提交包：公开MRI髌骨模型优化与六向回读实验

先打开“报告/报告.html”或“报告/实验报告.md”。模型样例位于model_samples/，其中STEP为Shell，IGS为Compound，不是已认证实体。

本包保留报告、五幅图、优化与六向CSV、源VTK及场景/许可、十组优化几何、六向转换文件、回读快照、逐项JSON/日志、39项回归记录和GUI证据，以及可复现源码。

精简范围：不包含数百MiB的完整随机采样数组、77MiB原始MRI图谱ZIP、Python虚拟环境和FreeCAD安装程序。全部采样数组仍在本机完整实验目录，地址见报告目录“完整结果位置.txt”。源ZIP可由脚本重新从官方地址下载，来源哈希在provenance.json中。

experiment/中的两个历史目录只保留关键JSON以说明首次索引问题与1,798面候选复测失败；完整历史仍在本机，未删除或覆盖。最终目录名称含verified。

重跑：进入reproduction/work/，按README建立Python环境、安装依赖并配置本机FreeCAD运行器，然后运行：

    PYTHONPATH=src .venv/bin/python scripts/experiments/medical_patella.py --phase all --out runs/reproduction

本次实际参数保存在最终experiment目录中的frozen_cad_config.json与optimization_plan.json。运行器中的本机路径需要按电脑调整。日志中的绝对路径保留原始证据，不为制作ZIP而重写；直接移动目录后GUI预览路径可能失效，重新运行会生成新路径。网页/MD与CSV不依赖这些绝对路径即可阅读。

数据：SPL Knee Atlas，Jen Richolt、Marianna Jakab、Ron Kikinis，SPL / Brigham and Women’s Hospital / Harvard Medical School。数据使用3D Slicer License section B；保留source/许可证与报告中的署名/修改声明。软件依赖各自遵循其许可，详见THIRD_PARTY_NOTICES.md。

仅为单一公开MRI图谱模型的研究与课程实验，未完成成员1完整自交/ROI/实体资格或临床验证。
'''
    manifest=[{'path':name,'bytes':src.stat().st_size,'sha256':hashlib.sha256(src.read_bytes()).hexdigest()} for name,src in sorted(mapping.items())]
    temporary=dest.with_suffix('.partial.zip')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('README_提交包说明.md',readme)
        for name,src in sorted(mapping.items()):z.write(src,name)
        z.writestr('BUNDLE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(temporary) as z:
        if z.testzip():raise ValueError('ZIP integrity test failed')
        for row in manifest:
            if hashlib.sha256(z.read(row['path'])).hexdigest()!=row['sha256']:
                raise ValueError('Bundle hash mismatch: '+row['path'])
    temporary.replace(dest)
    print(json.dumps({'package':str(dest),'files':len(manifest)+2,'bytes':dest.stat().st_size,'integrity':'passed'},ensure_ascii=False))


if __name__=='__main__':main()
