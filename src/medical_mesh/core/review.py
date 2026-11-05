"""Explicit human review of a validated repair candidate, separate from geometry."""
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime,timezone
import json


@dataclass
class CandidateReview:
    input_asset: object
    candidate: object
    result: dict
    output_dir: Path
    decision: str = 'pending'

    def __post_init__(self):
        if self.result.get('status')!='completed' or not self.result.get('accepted'):
            raise ValueError('Only a validated repair candidate can enter review')
        if self.candidate.parent_version!=self.input_asset.version:
            raise ValueError('Candidate does not belong to the current input version')
        if self.result.get('input_version')!=self.input_asset.version:
            raise ValueError('Task input version differs from the current version')
        if self.result.get('output_version')!=self.candidate.version:
            raise ValueError('Candidate version differs from task output')
        self.output_dir=Path(self.output_dir)
        self._save()

    def _save(self):
        self.output_dir.mkdir(parents=True,exist_ok=True)
        record=dict(decision=self.decision,input_version=self.input_asset.version,
                    candidate_version=self.candidate.version,
                    accepted_version=self.candidate.version if self.decision=='accepted' else self.input_asset.version,
                    time=datetime.now(timezone.utc).isoformat(),
                    note='Algorithm validation is separate from user acceptance')
        (self.output_dir/'review.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')

    def resolve(self,current_asset,accept):
        if self.decision!='pending':raise ValueError('Candidate has already been reviewed')
        if current_asset.version!=self.input_asset.version:raise ValueError('Current version changed during review')
        self.decision='accepted' if accept else 'discarded'
        self._save()
        return self.candidate if accept else self.input_asset


def comparison_rows(before,after):
    fields=[('顶点','vertex_count'),('三角面','face_count'),('边界环','boundary_loop_count'),('连通分量','component_count'),
            ('重复面','duplicate_face_count'),('退化面','degenerate_face_count'),
            ('非流形边','non_manifold_edge_count'),('非流形顶点','non_manifold_vertex_count'),
            ('方向冲突边','orientation_conflict_count')]
    return [(label,before['metrics'][key],after['metrics'][key]) for label,key in fields]
