import {Composition} from 'remotion';
import {AdComposition} from './AdComposition';
import {DEFAULT_PLAN, EditPlan} from './types';

const CROSSFADE_S = 0.4;

// Total duration = sum of segment durations minus crossfade overlaps.
const planDurationInFrames = (plan: EditPlan): number => {
  const overlaps = plan.segments.filter((s) => s.transition_in === 'crossfade').length;
  const total = plan.segments.reduce((a, s) => a + s.duration_s, 0) - overlaps * CROSSFADE_S;
  return Math.max(1, Math.round(total * plan.fps));
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Ad"
      component={AdComposition}
      defaultProps={{plan: DEFAULT_PLAN}}
      fps={DEFAULT_PLAN.fps}
      width={DEFAULT_PLAN.width}
      height={DEFAULT_PLAN.height}
      durationInFrames={planDurationInFrames(DEFAULT_PLAN)}
      calculateMetadata={({props}) => {
        const plan = (props as {plan: EditPlan}).plan;
        return {
          durationInFrames: planDurationInFrames(plan),
          fps: plan.fps,
          width: plan.width,
          height: plan.height,
        };
      }}
    />
  );
};
