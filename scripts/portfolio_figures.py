"""Editable SVG + 2x PNG from one saved run; Pillow is only a presentation dependency."""
import hashlib
import html
import json
import math
from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageFont

from ontime.replan import time_segments

ROOT = Path(__file__).resolve().parents[1]
BG, INK, MUTED, GRID = '#f7f6f2', '#142c3c', '#596b76', '#dae1e3'
COLORS = {'UAV-01': '#1876a3', 'UAV-02': '#28a2b5', 'AGV-01': '#b86525', 'AGV-02': '#d89938'}
ACTIVITY = {'depot_load': ('仓库装载', '#ddac50'), 'travel': ('行驶 / 返仓', '#247faa'),
            'wait': ('工位等待', '#9acbc1'), 'station_unload': ('工位卸载', '#66a897'),
            'service': ('工位服务', '#715d9c'), 'depot_unload': ('仓库卸载', '#d28659'),
            'turnaround': ('仓库周转', '#aaaeb2')}


class Canvas:
    def __init__(self, width, height, title, run, directory):
        self.width, self.height, self.directory = width, height, Path(directory)
        self.scale = 2
        self.image = Image.new('RGB', (width * 2, height * 2), BG)
        self.draw = ImageDraw.Draw(self.image)
        self.fonts = {}
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
                      '<title>' + html.escape(title) + '</title>',
                      '<metadata>' + html.escape(json.dumps({'input_sha256': run['input_snapshot_sha256'],
                        'parameters': run['parameters'], 'data_label': 'Illustrative data',
                        'source': '../run.json', 'map_kind': 'schematic only'}, ensure_ascii=False)) + '</metadata>',
                      '<defs><style>@font-face{font-family:"Source Han Sans CN";src:url("fonts/SourceHanSansCN-Regular.otf")} '
                      '@font-face{font-family:"Sarasa Mono SC";src:url("fonts/SarasaMonoSC-Regular.ttf")}</style></defs>']
        self.rect(0, 0, width, height, BG)
        self.text(42, 26, 'OnTime Dispatch', 18, MUTED, mono=True)
        self.text(42, 58, title, 31)
        p = run['parameters']
        self.text(42, 106, f'Illustrative data | mode={run["mode"]} | seed={p["seed"]} | population={p["population_size"]} | generations={run["generations_completed"]}/{p["max_generations"]}', 15, MUTED, mono=True)
        self.text(42, height - 57, '2026 新实现 · 功能演示 · 候选计划未经人工批准 · 非真实工厂 / 非部署结果', 15, MUTED)
        self.text(42, height - 30, f'input SHA256: {run["input_snapshot_sha256"]}', 12, MUTED, mono=True)

    def font(self, size, mono=False):
        key = size, mono
        if key not in self.fonts:
            file = 'SarasaMonoSC-Regular.ttf' if mono else 'SourceHanSansCN-Regular.otf'
            font = ImageFont.truetype(str(self.directory / 'fonts' / file), size * self.scale)
            expected = 'Sarasa Mono SC' if mono else 'Source Han Sans CN'
            if font.getname()[0] != expected:
                raise RuntimeError(f'Requested font mismatch: {font.getname()}')
            self.fonts[key] = font
        return self.fonts[key]

    def text(self, x, y, value, size=18, color=INK, mono=False):
        value = str(value)
        family = 'Sarasa Mono SC' if mono else 'Source Han Sans CN'
        self.parts.append(f'<text x="{x:.2f}" y="{y + size:.2f}" font-family="{family}" font-size="{size}" fill="{color}">{html.escape(value)}</text>')
        # Anchor to ascender: matching editable SVG baseline, no system font fallback.
        self.draw.text((x * 2, (y + size) * 2), value, fill=color, font=self.font(size, mono), anchor='ls')

    def rect(self, x, y, width, height, fill, stroke=None):
        self.parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" fill="{fill}"' + (f' stroke="{stroke}"' if stroke else '') + '/>')
        self.draw.rectangle((x * 2, y * 2, (x + width) * 2, (y + height) * 2), fill=fill, outline=stroke)

    def line(self, x1, y1, x2, y2, color=GRID, width=1, dashed=False):
        if dashed:
            length = math.hypot(x2 - x1, y2 - y1)
            for index in range(0, math.ceil(length), 12):
                if not length:
                    break
                a, b = index / length, min(index + 6, length) / length
                self.line(x1 + (x2-x1)*a, y1 + (y2-y1)*a,
                          x1 + (x2-x1)*b, y1 + (y2-y1)*b, color, width)
            return
        self.parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{color}" stroke-width="{width}"/>')
        self.draw.line((x1*2, y1*2, x2*2, y2*2), fill=color, width=max(1, round(width*2)))

    def circle(self, x, y, radius, fill, stroke=BG):
        self.parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        self.draw.ellipse(((x-radius)*2, (y-radius)*2, (x+radius)*2, (y+radius)*2), fill=fill, outline=stroke, width=4)

    def polygon(self, points, fill):
        self.parts.append('<polygon points="' + ' '.join(f'{x:.2f},{y:.2f}' for x,y in points) + f'" fill="{fill}"/>')
        self.draw.polygon([(x*2,y*2) for x,y in points], fill=fill)

    def save(self, name):
        svg, png = self.directory / f'{name}.svg', self.directory / f'{name}.png'
        svg.write_text('\n'.join([*self.parts, '</svg>']), encoding='utf-8')
        self.image.save(png, dpi=(300, 300))
        return {'name': name, 'svg': svg.name, 'png': png.name,
                'png_dimensions': [self.width*2, self.height*2], 'editable_text': True}


def render_figures(run_path, replan_path, directory):
    run = json.loads(Path(run_path).read_text(encoding='utf-8'))
    replan = json.loads(Path(replan_path).read_text(encoding='utf-8'))
    directory = Path(directory)
    (directory / 'fonts').mkdir(parents=True, exist_ok=True)
    for name in ('SourceHanSansCN-Regular.otf', 'SarasaMonoSC-Regular.ttf',
                 'SourceHanSans-LICENSE.txt', 'Sarasa-LICENSE.txt'):
        shutil.copyfile(ROOT / 'assets' / 'fonts' / name, directory / 'fonts' / name)
    source = run['input_snapshot']
    result = run['ga']
    figures = []

    c = Canvas(1240, 800, '仓库与工位：GA 候选路线示意', run, directory)
    c.text(42, 146, '坐标为合成布局（m）；连线表示访问关系，不表示真实障碍物规避路径。', 17, MUTED)
    points = source['metadata']['coordinates_m']
    def point(node):
        x,y = points[node]
        return 72 + x * 2.75, 650 - y * 2.35
    for v in range(0, 201, 50):
        c.line(72+v*2.75, 180, 72+v*2.75, 650)
        c.line(72, 650-v*2.35, 622, 650-v*2.35)
        c.text(66+v*2.75, 665, v, 13, MUTED, True)
        c.text(43, 640-v*2.35, v, 13, MUTED, True)
    c.text(562, 688, 'x (m)', 14, MUTED, True)
    c.text(82, 182, 'y (m)', 14, MUTED, True)
    for index, trip in enumerate(result['trips']):
        color = COLORS[trip['vehicle_id']]
        for leg in trip['legs']:
            x1,y1 = point(leg['from']); x2,y2 = point(leg['to'])
            c.line(x1,y1,x2,y2,color,2, trip['type']=='UAV')
            angle = math.atan2(y2-y1,x2-x1)
            x,y = x1+(x2-x1)*0.65,y1+(y2-y1)*0.65
            c.polygon([(x+6*math.cos(angle),y+6*math.sin(angle)),
                       (x-5*math.cos(angle)+4*math.sin(angle),y-5*math.sin(angle)-4*math.cos(angle)),
                       (x-5*math.cos(angle)-4*math.sin(angle),y-5*math.sin(angle)+4*math.cos(angle))],color)
        y = 193 + index*89
        c.rect(698,y+7,8,65,color)
        c.text(721,y,trip['trip_id'],18,color,True)
        c.text(721,y+29,' → '.join(n.replace('DEPOT','仓库') for n in trip['route']),17)
        c.text(721,y+54,f"载荷 {trip['payload_kg']:g}/{trip['capacity_kg']:g} kg · 行驶 {trip['travel_s']} s",16,MUTED)
    offsets = {'S01':(12,-19),'S02':(-94,-30),'S03':(-68,8),'S04':(15,-27),
               'S05':(14,3),'S06':(18,-1),'S07':(-74,-30),'S08':(15,2),'DEPOT':(12,-32)}
    unassigned_stations = {t['station_id'] for t in source['tasks'] if t['id'] in result['unassigned_task_ids']}
    for node in points:
        x,y=point(node)
        color = '#a93f48' if node in unassigned_stations else INK
        c.circle(x,y,7 if node!='DEPOT' else 10,color)
        dx,dy=offsets.get(node,(10,-15))
        c.text(x+dx,y+dy,'warehouse' if node=='DEPOT' else node,17,color,True)
    c.text(698,658,'未分配 T08：60 kg > 可用最大容量 50 kg',17,'#a93f48')
    c.text(698,686,'UAV 虚线 · AGV 实线 · 每趟均含返仓',16,MUTED)
    figures.append(c.save('01-routes'))

    def timeline(plan, title, filename, checkpoint=None):
        trips = sorted(plan['trips'], key=lambda t:(t['vehicle_id'],t['load_start_s']))
        height = 330 + 88 * len(trips)
        canvas = Canvas(1400,height,title,run,directory)
        maximum = max((t['planned_end_s'] for t in trips), default=1)
        limit = math.ceil(maximum/200)*200
        x0,xwidth,top=310,1030,233
        for tick in range(0,limit+1,200):
            x=x0+xwidth*tick/limit
            canvas.line(x,top-20,x,height-130)
            canvas.text(x-11,top-44,tick,14,MUTED,True)
        canvas.text(1288,top-71,'time (s)',14,MUTED,True)
        for i,(kind,(label,color)) in enumerate(ACTIVITY.items()):
            x=42+i*187
            canvas.rect(x,157,14,14,color)
            canvas.text(x+20,152,label,14,MUTED)
        for index, trip in enumerate(trips):
            y=top+index*88
            canvas.text(42,y,trip['vehicle_id'],18,COLORS[trip['vehicle_id']],True)
            canvas.text(42,y+26,trip['trip_id'],13,MUTED,True)
            canvas.text(42,y+48,','.join(trip['task_ids']),14,INK,True)
            if checkpoint is not None:
                status = '固定行程' if trip['trip_id'] in replan['frozen_trip_ids'] else '待批准新行程'
                canvas.text(168,y+48,status,13,'#a93f48' if status=='待批准新行程' else MUTED)
            for segment in time_segments(trip):
                start,end=segment['start_s'],segment['end_s']
                canvas.rect(x0+start/limit*xwidth,y+10,(end-start)/limit*xwidth,29,ACTIVITY[segment['kind']][1])
            canvas.text(x0+trip['load_start_s']/limit*xwidth,y-16,
                        f"{trip['load_start_s']} → {trip['planned_end_s']} s",13,MUTED,True)
        if checkpoint is not None:
            x=x0+checkpoint/limit*xwidth
            canvas.line(x,top-13,x,height-130,'#a93f48',2,True)
            canvas.text(x+6,top-18,f'checkpoint={checkpoint}s',14,'#a93f48',True)
        canvas.text(42,height-113,'横轴包含装载、工位等待 / 卸载 / 服务、返仓、仓库卸载；同车后续行程包含周转。',16,MUTED)
        canvas.text(42,height-86,'末趟未执行的周转不画入条形；设备初始不可用与仓库空闲表现为空白。',15,MUTED)
        return canvas.save(filename)
    figures.append(timeline(result,'按设备与行程排列的时间线','02-timeline'))

    c=Canvas(1440,795,'任务分配、服务开始窗与未分配原因',run,directory)
    c.text(42,146,'时间窗针对卸载 / 服务开始；soft 模式保留迟到。表格来自同一 GA 候选计划。',17,MUTED)
    columns=[42,112,202,296,454,609,752,852,944,1059]
    headers=['任务','工位','重量 kg','设备','行程序号','时间窗 s','到达 s','开始 s','迟到 s','状态 / 原因']
    c.rect(34,191,1370,45,INK)
    for x,label in zip(columns,headers): c.text(x,201,label,16,'#ffffff')
    stops={s['task_id']:(t,s) for t in result['trips'] for s in t['stops']}
    omitted={u['task_id']:u for u in result['unassigned']}
    for index,task in enumerate(source['tasks']):
        y=236+index*52
        c.rect(34,y,1370,52,'#ffffff' if index%2==0 else '#edf1ef')
        if task['id'] in stops:
            trip,stop=stops[task['id']]
            row=[task['id'],task['station_id'],f"{task['demand_kg']:g}",trip['vehicle_id'],
                 trip['trip_id'].rsplit('-',1)[-1],f"[{task['earliest_s']},{task['latest_s']}]",
                 stop['arrival_s'],stop['service_start_s'],stop['lateness_s'],
                 '候选 · 迟到' if stop['lateness_s'] else '候选 · 窗内']
        else:
            row=[task['id'],task['station_id'],f"{task['demand_kg']:g}",'—','—',
                 f"[{task['earliest_s']},{task['latest_s']}]",'—','—','—',omitted[task['id']]['reason_code']]
        for j,(x,value) in enumerate(zip(columns,row)):
            c.text(x,y+14,value,16,'#a93f48' if task['id'] in omitted else INK,mono=j<9 or task['id'] in omitted)
    c.text(42,677,'T08 未分配：所有可用且适配的设备容量均小于 60 kg；不会通过违规装载提高覆盖。',17,'#a93f48')
    figures.append(c.save('03-task-table'))

    c=Canvas(1240,845,'启发式与 GA：同算例的实际比较',run,directory)
    c.text(42,148,'先比较未分配数，再比较运输 + 迟到罚值。演示罚值不代表实测经济成本。',17,MUTED)
    c.rect(42,194,1156,45,INK)
    for x,label in zip((63,512,731,940),('指标 / 单位','启发式','GA','GA − 启发式')): c.text(x,204,label,18,'#ffffff')
    labels={'assigned_count':'已分配任务 / count','unassigned_count':'未分配任务 / count',
            'trip_count':'行程 / count','travel_s':'行驶（含返仓）/ s','waiting_s':'工位等待 / s',
            'lateness_s':'迟到 / s','transport_cost':'运输罚值 / penalty_unit',
            'lateness_penalty':'迟到罚值 / penalty_unit','total_cost':'总罚值 / penalty_unit'}
    rows=[r for r in run['comparison']['metrics'] if r['metric'] in labels]
    for i,row in enumerate(rows):
        y=239+i*43
        c.rect(42,y,1156,43,'#ffffff' if i%2==0 else '#edf1ef')
        c.text(63,y+10,labels[row['metric']],17)
        for x,key in ((512,'initial'),(731,'ga'),(940,'delta_ga_minus_initial')):
            c.text(x,y+10,f"{row[key]:g}",18,INK,True)
    c.text(42,647,f"本次严格改善：{'是' if run['comparison']['improved'] else '否'}；最优首次记录在代 {run['best_found_generation']}。",20)
    c.text(42,683,f"停止：{run['stop_reason']}；已执行繁殖代数 {run['generations_completed']}；2-opt 未实现。",17,MUTED)
    c.text(42,720,'这些数字只描述本次输入、模式、参数与种子；不构成普遍提升或近似最优结论。',16,MUTED)
    figures.append(c.save('04-comparison'))

    c=Canvas(1240,820,'GA 迭代记录：每代实际最优目标',run,directory)
    initial=run['initial']['objective']['total_cost']
    vals=[r['best_known']['total_cost'] for r in run['iterations']]
    lo,hi=min([initial,*vals]),max([initial,*vals])
    pad=max(0.025,(hi-lo)*0.3); lo-=pad;hi+=pad
    x0,y0,w,h=123,214,1060,325
    def xy(gen,val): return x0+w*gen/max(1,run['generations_completed']),y0+h-(val-lo)/(hi-lo)*h
    c.text(42,148,'下图罚值纵轴局部放大；未分配任务数另列，避免混用两个目标的单位。',17,MUTED)
    for i in range(5):
        val=lo+(hi-lo)*i/4;y=xy(0,val)[1]
        c.line(x0,y,x0+w,y)
        c.text(42,y-11,f'{val:.3f}',14,MUTED,True)
    c.text(42,183,'penalty_unit',13,MUTED,True)
    c.line(*xy(0,initial),*xy(run['generations_completed'],initial),'#b86525',2,True)
    c.text(x0+20,xy(0,initial)[1]-29,f'第一阶段：{initial:g}',17,'#b86525')
    previous=None
    for row in run['iterations']:
        pt=xy(row['generation'],row['best_known']['total_cost'])
        if previous: c.line(*previous,*pt,'#1876a3',3)
        c.circle(*pt,4,'#1876a3')
        previous=pt
        c.text(pt[0]-6,y0+h+13,row['generation'],13,MUTED,True)
        c.text(pt[0]-6,610,row['best_known']['unassigned_count'],16,INK,True)
        # Generation best is also shown; if equal, a small diamond shares the same actual point.
        px,py=xy(row['generation'],row['generation_best']['total_cost'])
        c.polygon([(px,py-4),(px+4,py),(px,py+4),(px-4,py)],'#28a2b5')
    c.text(42,579,'未分配 / count',16,MUTED)
    c.text(1110,568,'generation',14,MUTED,True)
    c.text(42,657,'蓝线 / 圆点：累计最优；青色菱形：当代最优；橙色虚线：第一阶段参考值。',16,MUTED)
    c.text(42,690,f"代 0 包含初始种群搜索；实际记录 {len(run['iterations'])} 个点；曲线没有补造改善。",16,MUTED)
    c.text(42,720,f"停止原因：{run['stop_reason']}；首次最优代：{run['best_found_generation']}。",16,MUTED)
    figures.append(c.save('05-ga-iterations'))

    figures.append(timeline(replan['combined'],'设备不可用后：固定历史与待批准新计划','06-replan-timeline',replan['checkpoint_s']))
    info={'input_sha256':run['input_snapshot_sha256'], 'figures':figures,
          'fonts':{name:hashlib.sha256((directory/'fonts'/name).read_bytes()).hexdigest()
                   for name in ('SourceHanSansCN-Regular.otf','SarasaMonoSC-Regular.ttf')},
          'renderer':'Pillow using the same drawing primitives as editable SVG; 2x pixels, 300 dpi metadata',
          'no_font_fallback':True, 'source_run':'../run.json', 'replan_source':'../replan/replan.json'}
    (directory/'figure-manifest.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    return figures
