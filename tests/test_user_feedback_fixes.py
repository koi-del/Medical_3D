from medical_mesh.io.mesh_io import load_mesh
from medical_mesh import detect_defects
from medical_mesh.ui.boundary_advice import boundary_advice
from medical_mesh.member2.reporting import render_report


def test_small_hole_advice_does_not_classify_large_pipe_ends_as_defects():
    small=load_mesh('data/damaged/hole.npz');pipe=load_mesh('data/reference/open_tube.npz')
    assert boundary_advice(small,detect_defects(small).boundaries)[0]['role']=='repair_target'
    assert all(x['role']=='uncertain' for x in boundary_advice(pipe,detect_defects(pipe).boundaries))


def test_user_report_omits_raw_payload_and_explains_metrics(tmp_path):
    render_report(dict(operation='evaluate',status='completed',quality_status='unverified',
        decision='not_applicable',metrics=dict(asd=.01,d95=.02,sampled_max=.03)),tmp_path)
    report=(tmp_path/'report.html').read_text(encoding='utf-8')
    assert '完整记录' not in report and '<pre>' not in report
    assert '指标释义' in report and '双向表面误差评价' in report
    assert (tmp_path/'result.json').exists()
