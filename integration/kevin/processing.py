"""Pure derived geometry; no clinical thresholds or patient model."""
import math


def relative_orientation(channels, max_skew_s=0.1):
    result = {'value': None, 'unit': 'degree', 'valid': False,
              'meaning': 'relative sensor rotation magnitude; not anatomical neck angle'}
    head, chest = channels.get('head_imu'), channels.get('chest_imu')
    if not head or not chest or not head['valid'] or not chest['valid']:
        return dict(result, reason='two valid orientation samples required')
    a, b = head['timing'], chest['timing']
    if a['mapped_host_s'] is None or b['mapped_host_s'] is None:
        return dict(result, reason='clock mappings unavailable')
    if abs(a['mapped_host_s']-b['mapped_host_s']) + a['uncertainty_s'] + b['uncertainty_s'] > max_skew_s:
        return dict(result, reason='samples not sufficiently time aligned')
    hm, cm = head['meta'], chest['meta']
    if not hm.get('frame_id') or hm.get('frame_id') != cm.get('frame_id') or not (hm.get('mounting_calibrated') is True and cm.get('mounting_calibrated') is True):
        return dict(result, reason='coordinate frames/mounting not verified')
    q, r = head['value'], chest['value']
    if not isinstance(q, list) or not isinstance(r, list) or len(q) != 4 or len(r) != 4:
        return dict(result, reason='quaternion input required')
    # abs(dot) is invariant under the q/-q equivalence of unit quaternions.
    dot = abs(sum(x*y for x, y in zip(q, r))) / math.sqrt(sum(x*x for x in q)*sum(y*y for y in r))
    return dict(result, value=math.degrees(2*math.acos(min(1.0, dot))), valid=True,
                reason=None, simulated=head['simulated'] or chest['simulated'])
