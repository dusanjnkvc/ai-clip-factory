// Adapted from Remotion Basic Captions; see THIRD_PARTY_LICENSES.md.
import type {Caption} from '@remotion/captions';
import {createTikTokStyleCaptions} from '@remotion/captions';
import React, {useMemo} from 'react';
import type {CaptionStyle} from '../lib/editor-project';
import {
	Interactive,
	useCurrentFrame,
	useVideoConfig,
	type InteractiveTransformProps,
	type InteractivitySchema,
	type SequenceProps,
} from 'remotion';

type BasicCaptionsProps = InteractiveTransformProps &
	Pick<SequenceProps, 'width'> & {
		readonly captions: Caption[];
		readonly appearance?: CaptionStyle;
		readonly combineTokensWithinMilliseconds?: number;
	};

const defaultCombineTokensWithinMilliseconds = 3000;
const defaultWidth = 900;

const basicCaptionsSchema = {
	...Interactive.captionsSchema,
	width: {
		type: 'number',
		min: 1,
		step: 1,
		default: undefined,
		description: 'Caption area width',
		hiddenFromList: false,
	},
	combineTokensWithinMilliseconds: {
		type: 'number',
		min: 0,
		step: 50,
		default: defaultCombineTokensWithinMilliseconds,
		description: 'Time between caption pages',
		hiddenFromList: false,
	},
} as const satisfies InteractivitySchema;

const BasicCaptionsContent: React.FC<BasicCaptionsProps> = ({
	captions,
	combineTokensWithinMilliseconds = defaultCombineTokensWithinMilliseconds,
	style,
	appearance,
	width = defaultWidth,
}) => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();
	const pages = useMemo(
		() =>
			createTikTokStyleCaptions({
				captions,
				combineTokensWithinMilliseconds,
			}).pages,
		[captions, combineTokensWithinMilliseconds],
	);
	const currentTimeMs = (frame / fps) * 1000;
	const page = pages.find(
		(candidate) =>
			currentTimeMs >= candidate.startMs &&
			currentTimeMs < candidate.startMs + candidate.durationMs,
	);

	return (
		<div
			style={{
				alignItems: 'center',
				display: 'flex',
				justifyContent: 'center',
				width,
				...style,
			}}
		>
			{page ? (
				<div
					style={{
						backgroundColor: 'rgba(64, 64, 64, 0.75)',
						color: style?.color ?? '#ffffff',
						fontFamily: appearance?.font_family && appearance.font_family!=='Noto Sans' ? appearance.font_family : 'ClipFactoryCaption, Arial, sans-serif',
						fontSize: appearance ? appearance.size * Number(width) / 936 : style?.fontSize ?? 64,
						fontWeight: appearance?.weight ?? 400,
						lineHeight: appearance?.line_height ?? 1.2,
						...(appearance ? {color:appearance.color,backgroundColor:appearance.background,opacity:appearance.opacity*(appearance.animation==='fade'?Math.min(1,(currentTimeMs-page.startMs)/100,(page.startMs+page.durationMs-currentTimeMs)/100):1),rotate:`${appearance.rotation}deg`,letterSpacing:appearance.letter_spacing,WebkitTextStroke:`${appearance.outline_width}px ${appearance.outline}`,paintOrder:'stroke fill',textTransform:appearance.uppercase?'uppercase' as const:'none' as const,scale:appearance.animation==='pop'?Math.min(1,.85+(currentTimeMs-page.startMs)/1000):1} : {}),
						padding: '14px 22px',
						textAlign: appearance?.align || 'center',
						textShadow: appearance?.shadow===false ? 'none' : '0 3px 8px #000000B0',
						textWrap: 'balance',
						whiteSpace: 'pre-wrap',
					}}
				>
					{appearance?.animation==='karaoke'?page.tokens.map((token,index)=><span key={index} style={{color:currentTimeMs>=token.fromMs&&currentTimeMs<token.toMs?appearance.highlight:appearance.color}}>{token.text}</span>):page.text.trim()}
				</div>
			) : null}
		</div>
	);
};

export const BasicCaptions = Interactive.create({
	Component: BasicCaptionsContent,
	componentName: '<BasicCaptions>',
	schema: basicCaptionsSchema,
});
