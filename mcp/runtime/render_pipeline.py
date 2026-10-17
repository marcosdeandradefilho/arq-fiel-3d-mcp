"""One-step metric reconstruction and physically-based Blender Cycles rendering.

Runs ONLY where Blender is installed: not in the Vercel Python function.
Never certifies as-built accuracy, structural integrity or photographic identity.
"""
import json
import pathlib
from core import build_scene, render_views, validate_project


def build_and_render_physical(project, output_dir, samples=128, blender_executable='blender'):
    """Validate source -> build metric GLB -> render all planned room cameras.

    Raises rather than claiming a photoreal render when Cycles is unavailable.
    Retains GLB and audits if rendering fails, for reproducible diagnosis.
    """
    validation = validate_project(project)
    if not validation['ok']:
        raise ValueError('Projeto geométrico inválido: ' + '; '.join(validation['errors']))
    if validation['fidelity'] != 'plant-validated-not-as-built':
        raise ValueError('Renderização arquitetônica requer escala e dimensões explicitamente confirmadas.')
    if type(samples) is not int or not 16 <= samples <= 1024:
        raise ValueError('Cycles samples deve estar entre 16 e 1024.')
    target = pathlib.Path(output_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    built = build_scene(project, str(target))
    images_dir = target / 'renders_ciclos'
    physical = render_views(built['model_glb'], built['views_json'], str(images_dir),
                            blender_executable=blender_executable, samples=samples)
    expected = len(project['rooms'])
    if len(physical.get('pngs', [])) != expected:
        raise RuntimeError(f'Render incompleto: {len(physical.get("pngs", []))} de {expected} ambientes.')
    audit = {
        'status': 'physically-rendered-not-as-built',
        'source_geometry_fidelity': validation['fidelity'],
        'renderer': physical['renderer'],
        'rooms_expected': expected,
        'rooms_rendered': len(physical['pngs']),
        'samples_per_pixel': samples,
        'photographic_identity_guaranteed': False,
        'as_built_verified': False,
        'missing_evidence_not_inferred': True,
        'limits': ['Texturas, superfícies, iluminação e geometria oculta dependem de referências confirmadas.',
                   'Render por Cycles não comprova fidelidade a um imóvel construído.']
    }
    audit_path = target / 'render_audit.json'
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    return {**built, 'physical_renders': physical['pngs'], 'renderer': physical['renderer'],
            'render_manifest': str(images_dir / 'render_manifest.json'),
            'render_audit': str(audit_path), 'render_validation': audit}
