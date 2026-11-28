#!/bin/bash
# مونتير ⚡ ترميز وضع الطبقة: cutz.mp4 + كابشن PNG شفاف (ovl/list.txt) + شريط التقدّم بـffmpeg + فريمات الخاتمة (out/) + الصوت
set -e
. "$(dirname "$0")/_compat.sh"
W="$(abspath "$1")"; OUT="${2:-$W/ad-final.mp4}"
read VEND OD INK ACC BAR <<<$("$PY" -c "
import json;c=json.load(open('$W/caps.json'));s=json.load(open('$W/sfx.json'));t=json.load(open('$W/theme.json')) if __import__('os').path.exists('$W/theme.json') else {}
print(round(c['total'],3),float(s.get('outro',0) or 0),t.get('ink','#1F1F1D').lstrip('#'),t.get('acc','#D97757').lstrip('#'),0 if t.get('bar') is False else 1)")
DUR=$("$PY" -c "print(round($VEND+$OD,3))"); FADE=$("$PY" -c "print(round($DUR-0.6,3))"); BE=$("$PY" -c "print(round($VEND-0.3,3))")
BARF=""; [ "$BAR" = 1 ] && BARF=",drawbox=x=60:y=1492:w=960:h=7:color=0x${INK}@0.13:t=fill:enable='lt(t,$BE)',drawbox=x=60:y=1492:w='max(1,960*t/$VEND)':h=7:color=0x${ACC}:t=fill:enable='lt(t,$BE)'"
# الطبقة sRGB → bt709 قبل التركيب (نفس دقة VF_ENCODE) — بدونها ألوان الكابشن تنحرف
FC="[0:v]trim=0:$VEND,setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv420p[bv];\
[1:v]fps=30,setsar=1,format=rgba,scale=out_color_matrix=bt709:out_range=tv,format=yuva420p[ov];\
[bv][ov]overlay=0:0:eof_action=pass:format=yuv420${BARF}[main];\
[2:v]fps=30,setsar=1,${VF_ENCODE}[ou];[main][ou]concat=n=2:v=1:a=0[vo];\
[0:a]apad=pad_dur=8[a0];[a0][3:a]amix=inputs=2:duration=first:normalize=0[am];[am]atrim=0:$DUR,asetpts=PTS-STARTPTS,afade=t=out:st=$FADE:d=0.6[ao]"
echo "⚡ أركّب الطبقة على الفيديو…"
ffmpeg -v error -nostats -i "$W/cutz.mp4" -f concat -safe 0 -i "$W/ovl/list.txt" -framerate 30 -i "$W/out/%05d.jpg" -i "$W/sfx.wav" \
  -filter_complex "$FC" -map "[vo]" -map "[ao]" \
  -c:v libx264 -preset ${X264_PRESET:-veryfast} -profile:v high -level 4.0 -pix_fmt yuv420p -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709 -r 30 \
  -bsf:v h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1:video_full_range_flag=0 \
  -crf 21 -maxrate 6M -bufsize 12M -c:a aac -b:a 160k -ar 48000 -movflags +faststart -y "$OUT"
echo "✅ $OUT"
