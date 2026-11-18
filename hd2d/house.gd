extends Node3D
## 房子模式：住宅區第一棟透天厝的骨架（docs/FIRST_BUILD.md 第三節「房子」）。
## main.gd 看到啟動參數 --house 就把這個節點加進去，其他什麼都不建。
##
## 啟動參數（寫在 -- 後面）：
##   --house                 進這個模式
##   --at=<房間代號>[,dx,dz]  開場把玩家放在那間房（alley、bedroom、living、kitchen、garage、kids、hall、master、bath、attic）
##   --at=stairs1:0.5        放在第一段樓梯（一樓到二樓）的一半；stairs2 是二樓到三樓。dx、dz 也可以用冒號分隔
##   --noise                 一開場就顯示跑步的聲音半徑（給截圖檢查用）
##   --wide                  鏡頭拉遠到看得見整層樓，不跟著人走（檢查格局用，景深關掉）
##   --shot=路徑.png [--shot-frames=30]   截圖後結束
##
## 座標：x 向右，z 朝鏡頭，y 向上。鏡頭固定朝 -z 看，所以每層樓的房間左右排成一列，
## 靠鏡頭那面牆（前牆）在玩家進屋後切到只剩一截矮牆。樓層是真的疊在一起的，玩家所在樓層以上的都隱藏。
##
## 格局是下面幾張資料表：ROOMS（房間）、DOORS（門）、STAIRS（樓梯）、PLACES（家具擺哪）。改格局改表就好。
## 家具：art/furniture/<代號>_front.png 存在就用圖，不存在就放 FURN 表裡那個尺寸的素色方塊。

const Kit := preload("res://kit.gd")
const PX := Kit.SHEET_PIXEL

const D := 6.0                          # 每間房的深度（z 方向），整棟一樣
const WALL_H := 3.2
const WALL_T := 0.2
const STEPS := 14                       # 一段樓梯幾級
const STEP_RISE := 9 * PX               # 一級階梯：45 × 9 × 13 像素
const STEP_RUN := 13 * PX
const STEP_W := 45 * PX
const FLOOR_H := STEPS * STEP_RISE      # 樓層高度 = 十四級階梯（約 3.375）
const SLAB := FLOOR_H - WALL_H          # 樓板厚度
const DOOR_PX := Vector3(45, 105, 2)    # 室內門
const ALLEY_D := 5.0                    # 巷子的寬度（z 方向）
const ALLEY_X := 17.0                   # 巷子左右兩頭的圍牆
const BACK := -99.0                     # PLACES 裡 z 寫這個代表「貼著後牆」
const SPEED := 2.8
const RUN_SPEED := 4.6
const NOISE_WALK := 1.5                 # 走路的聲音半徑
const NOISE_RUN := 5.0                  # 跑步的聲音半徑
const WALKER_SPEED := 1.0
const NO_TARGET := Vector2(INF, INF)

# 房間。x 是左邊牆的位置，w 是寬度；z 方向全部是 -D/2 到 D/2。floor 0 是一樓。
# tile、wall 是 art/tiles/ 裡的貼圖名字（還沒交的用 TILES 表裡的顏色暫代）。win 是後牆上的窗（離左牆多遠）。
const ROOMS := [
	{"id": "bedroom", "name": "臥室", "floor": 0, "x": -15.0, "w": 6.0, "tile": "floor_planks", "win": [4.4]},
	{"id": "living", "name": "客廳", "floor": 0, "x": -9.0, "w": 10.0, "tile": "floor_planks", "win": [1.9]},
	{"id": "kitchen", "name": "廚房", "floor": 0, "x": 1.0, "w": 6.0, "tile": "floor_tile_kitchen", "win": [3.6]},
	{"id": "garage", "name": "車庫", "floor": 0, "x": 7.0, "w": 8.0, "tile": "floor_concrete", "light": Color(0.8, 0.88, 1.0)},
	{"id": "kids", "name": "小孩房", "floor": 1, "x": -15.0, "w": 6.0, "tile": "floor_planks", "win": [1.3]},
	{"id": "hall", "name": "二樓樓梯廳", "floor": 1, "x": -9.0, "w": 10.0, "tile": "floor_planks", "win": [1.6]},
	{"id": "master", "name": "主臥", "floor": 1, "x": 1.0, "w": 6.0, "tile": "floor_planks", "win": [2.1]},
	{"id": "bath", "name": "浴室", "floor": 1, "x": 7.0, "w": 5.0, "tile": "floor_tile_bath", "wall": "wall_tile_bath", "light": Color(0.9, 0.95, 1.0)},
	{"id": "attic", "name": "閣樓", "floor": 2, "x": -9.0, "w": 10.0, "tile": "floor_attic", "dark": true},
]

# 門。axis "z"：開在左右兩間房中間的牆上（x 是那面牆的位置，z 是門的中心）。
# axis "x"：開在前牆上（z 是前牆的位置，x 是門的中心）。locked 的打不開，撞上去顯示 msg。
const DOORS := [
	{"id": "front", "floor": 0, "axis": "x", "x": -7.0, "z": 3.0, "art": "door_front", "px": Vector3(50, 108, 3)},
	{"id": "bedroom_living", "floor": 0, "axis": "z", "x": -9.0, "z": 0.6},
	{"id": "living_kitchen", "floor": 0, "axis": "z", "x": 1.0, "z": 0.6},
	{"id": "kitchen_garage", "floor": 0, "axis": "z", "x": 7.0, "z": 0.6, "locked": true, "msg": "車庫的門鎖著。"},
	{"id": "kids_hall", "floor": 1, "axis": "z", "x": -9.0, "z": 0.6},
	{"id": "hall_master", "floor": 1, "axis": "z", "x": 1.0, "z": 0.6},
	{"id": "master_bath", "floor": 1, "axis": "z", "x": 7.0, "z": 0.6},
]

# 樓梯。都沿著 x 方向，從 STAIR_X0 開始，長度是十四級。floor 是下面那一層。
# dir 1：往右走是上樓；dir -1：往左走是上樓。兩段一前一後錯開，上到二樓轉個身接著上三樓。
const STAIR_X0 := -5.8
const STAIRS := [
	{"id": "stairs1", "floor": 0, "z": -D / 2 + WALL_T / 2, "dir": 1},
	{"id": "stairs2", "floor": 1, "z": -D / 2 + WALL_T / 2 + STEP_W + 0.1, "dir": -1},
]

# 還沒交圖的貼圖：暫代的顏色和格線（像素）。
const TILES := {
	"floor_tile_kitchen": [Color(0.78, 0.76, 0.70), 16],
	"floor_tile_bath": [Color(0.60, 0.72, 0.76), 8],
	"wall_tile_bath": [Color(0.84, 0.89, 0.91), 8],
	"floor_concrete": [Color(0.50, 0.50, 0.50), 0],
	"floor_attic": [Color(0.55, 0.45, 0.33), 0],
	"floor_asphalt": [Color(0.20, 0.20, 0.22), 0],
	"wall_exterior": [Color(0.72, 0.68, 0.62), 0],
	"shutter_front": [Color(0.55, 0.57, 0.60), 4],
	"neighbor_a": [Color(0.62, 0.60, 0.58), 0],
	"neighbor_b": [Color(0.70, 0.62, 0.55), 0],
	"roof": [Color(0.30, 0.30, 0.33), 0],
}

# 家具的像素尺寸（寬 × 高 × 深）和佔位方塊的顏色。尺寸照 docs/FIRST_BUILD.md 第二節。有圖的以圖為準。
const FURN := {
	"sofa_seat": [Vector3(94, 19, 40), Color(0.35, 0.45, 0.62)],
	"sofa_back": [Vector3(94, 21, 9), Color(0.35, 0.45, 0.62)],
	"coffee_table": [Vector3(54, 22, 27), Color(0.80, 0.62, 0.40)],
	"tv_console": [Vector3(68, 22, 22), Color(0.90, 0.88, 0.82)],
	"moving_box": [Vector3(27, 20, 20), Color(0.80, 0.62, 0.42)],
	"tv": [Vector3(55, 32, 4), Color(0.08, 0.08, 0.10)],
	"shoe_cabinet": [Vector3(40, 50, 18), Color(0.82, 0.78, 0.70)],
	"counter_sink": [Vector3(45, 42, 30), Color(0.80, 0.83, 0.86)],
	"counter_stove": [Vector3(45, 42, 30), Color(0.66, 0.68, 0.72)],
	"fridge": [Vector3(35, 88, 35), Color(0.88, 0.90, 0.92)],
	"dining_table": [Vector3(60, 38, 40), Color(0.72, 0.55, 0.36)],
	"chair_seat": [Vector3(22, 22, 22), Color(0.62, 0.46, 0.30)],
	"chair_back": [Vector3(22, 22, 3), Color(0.62, 0.46, 0.30)],
	"bed_single": [Vector3(50, 22, 100), Color(0.72, 0.78, 0.88)],
	"bed_single_head": [Vector3(50, 45, 3), Color(0.55, 0.42, 0.30)],
	"wardrobe": [Vector3(50, 95, 30), Color(0.60, 0.47, 0.33)],
	"nightstand": [Vector3(22, 25, 20), Color(0.60, 0.47, 0.33)],
	"garage_shelf": [Vector3(60, 90, 22), Color(0.45, 0.47, 0.50)],
	"workbench": [Vector3(75, 42, 30), Color(0.50, 0.42, 0.32)],
	"toolbox": [Vector3(25, 15, 12), Color(0.75, 0.20, 0.18)],
	"car_body": [Vector3(215, 38, 88), Color(0.74, 0.76, 0.80)],
	"car_cabin": [Vector3(120, 30, 80), Color(0.24, 0.29, 0.36)],
	"bed_double": [Vector3(80, 22, 100), Color(0.86, 0.82, 0.76)],
	"bed_double_head": [Vector3(80, 45, 3), Color(0.50, 0.38, 0.28)],
	"dresser": [Vector3(50, 40, 22), Color(0.70, 0.56, 0.42)],
	"desk": [Vector3(50, 38, 28), Color(0.78, 0.66, 0.48)],
	"toy_box": [Vector3(30, 20, 20), Color(0.92, 0.70, 0.25)],
	"bookshelf_low": [Vector3(40, 50, 15), Color(0.78, 0.66, 0.48)],
	"toilet_bowl": [Vector3(20, 20, 25), Color(0.93, 0.93, 0.92)],
	"toilet_tank": [Vector3(20, 20, 9), Color(0.93, 0.93, 0.92)],
	"sink_cabinet": [Vector3(30, 42, 22), Color(0.88, 0.88, 0.86)],
	"bathtub": [Vector3(75, 28, 35), Color(0.93, 0.94, 0.95)],
	"washing_machine": [Vector3(30, 42, 30), Color(0.82, 0.84, 0.86)],
	"storage_bin": [Vector3(30, 18, 20), Color(0.30, 0.55, 0.70)],
	"trash_bin": [Vector3(20, 30, 20), Color(0.24, 0.40, 0.30)],
	"stair_step": [Vector3(45, 9, 13), Color(0.62, 0.50, 0.38)],
	"door_interior": [DOOR_PX, Color(0.82, 0.74, 0.60)],
	"door_front": [Vector3(50, 108, 3), Color(0.34, 0.38, 0.44)],
	# 立牌（透明底單張 art/furniture/<代號>.png）。還沒交的用薄方塊佔位
	"desk_lamp": [Vector3(26, 42, 6), Color(0.9, 0.9, 0.85)],
	"scooter": [Vector3(70, 45, 26), Color(0.72, 0.20, 0.20)],
	"plant_pot": [Vector3(18, 40, 18), Color(0.25, 0.50, 0.28)],
	"street_lamp": [Vector3(6, 150, 6), Color(0.30, 0.30, 0.32)],
}
const STANDEES := ["desk_lamp", "scooter", "plant_pot", "street_lamp"]

# 由幾件拼起來的家具：每件 [代號, 相對於第一件底面中心的位移（像素：右、上、前）]
const COMPOSITES := {
	"sofa": [["sofa_seat", Vector3.ZERO], ["sofa_back", Vector3(0, 19, -15.5)]],
	"chair": [["chair_seat", Vector3.ZERO], ["chair_back", Vector3(0, 22, -9.5)]],
	"bed_single_set": [["bed_single", Vector3.ZERO], ["bed_single_head", Vector3(0, 0, -51.5)]],
	"bed_double_set": [["bed_double", Vector3.ZERO], ["bed_double_head", Vector3(0, 0, -51.5)]],
	"toilet": [["toilet_bowl", Vector3.ZERO], ["toilet_tank", Vector3(0, 20, -8)]],
	"car": [["car_body", Vector3.ZERO], ["car_cabin", Vector3(8, 38, 0)]],
}

# 家具擺哪：每筆 [代號, 離房間左牆多遠, z（或 BACK = 貼後牆）, 轉幾度（省略 = 0）, 墊高幾像素（省略 = 0）]
const PLACES := {
	"living": [
		["tv_console", 1.5, BACK], ["desk_lamp", 1.1, -2.6, 0, 22],
		["sofa", 5.6, -1.06], ["coffee_table", 5.6, 0.25],
		["shoe_cabinet", 0.36, 2.3, 90],
		["moving_box", 9.3, 2.3, 8], ["moving_box", 8.5, 2.45, -12], ["moving_box", 9.2, 2.35, 20, 20],
	],
	"kitchen": [
		["counter_sink", 0.8, BACK], ["counter_stove", 2.02, BACK], ["fridge", 5.2, BACK],
		["dining_table", 3.2, -0.8], ["chair", 2.0, -0.8, 90], ["chair", 4.4, -0.8, -90],
	],
	"bedroom": [
		["bed_single_set", 1.2, BACK], ["nightstand", 2.3, BACK], ["wardrobe", 4.6, BACK],
	],
	"garage": [
		["car", 4.8, -1.3], ["garage_shelf", 1.05, BACK],
		["workbench", 7.45, 1.7, -90], ["toolbox", 7.45, 1.7, -90, 42],
	],
	"kids": [
		["bed_single_set", 1.2, BACK], ["desk", 3.2, BACK], ["chair", 3.2, -1.75, 180],
		["bookshelf_low", 4.9, BACK], ["toy_box", 1.0, 2.2],
	],
	"hall": [
		["moving_box", 0.8, 2.3, 15],
	],
	"master": [
		["nightstand", 0.6, BACK], ["bed_double_set", 2.1, BACK], ["nightstand", 3.6, BACK], ["wardrobe", 4.9, BACK],
		["dresser", 0.46, 2.2, 90],
	],
	"bath": [
		["bathtub", 1.2, BACK], ["toilet", 2.8, BACK], ["sink_cabinet", 3.8, BACK],
		["washing_machine", 4.45, 2.2, -90],
	],
	"attic": [
		["storage_bin", 1.0, BACK], ["storage_bin", 1.9, BACK], ["storage_bin", 1.45, BACK, 0, 18],
		["moving_box", 8.5, -2.0, 10], ["moving_box", 9.2, 0.6, -20], ["moving_box", 9.1, 0.6, 25, 20],
		["storage_bin", 6.0, 2.2, 5], ["moving_box", 2.4, 1.6, -30],
	],
	"alley": [                               # 巷子：第二個數字直接是 x
		["plant_pot", -8.2, 3.75], ["scooter", -3.6, 4.0], ["trash_bin", -1.6, 3.85], ["trash_bin", -0.9, 3.9, 12],
		["street_lamp", 3.0, 3.8],
	],
}

var floor_nodes: Array[Node3D] = []      # 0～2 是樓層；3 只放最上面的屋頂
var front_full: Array[Node3D] = []       # 每層的前牆（完整的，從巷子看）
var front_stub: Array[Node3D] = []       # 每層的前牆（進屋後換成這截矮牆）
var walks: Array = [[], [], []]          # 每層能走的範圍（Rect2，x、z 平面，已經扣掉牆和人的半徑）
var obstacles: Array = [[], [], []]      # 每層擋路的家具
var doors: Array = []                    # 執行期的門：{def, pivot, angle, bridge, center, floor, locked}
var stairs: Array = []                   # 執行期的樓梯：{floor, dir, rect}
var room_lights := {}                    # 房間代號 → 那間的燈
var walkers: Array = []                  # 行屍：{sprite, pos, target, t}
var tile_cache := {}

var env: Environment
var cam: Camera3D
var moon: DirectionalLight3D
var fill: DirectionalLight3D
var torch: OmniLight3D                   # 暗的房間裡跟著玩家的小燈（之後換成手電筒）
var ring: MeshInstance3D                 # 聲音半徑
var player: Sprite3D
var pos := Vector3(-7.0, 0, 5.2)         # 玩家的位置。y 不用，高度由樓層和樓梯算
var floor_i := 0                         # 玩家在哪一層
var on_stair := -1                       # 正在哪一段樓梯上（-1 = 不在）
var target := NO_TARGET                  # 點地板要走去的位置
var walk_t := 0.0
var dark_k := 0.0                        # 0 = 一般，1 = 在暗的房間裡
var last_view := ""
var msg_until := 0

var info: Label
var where: Label
var msg: Label
var zh_font: SystemFont
var shot_path := ""
var shot_after := 30
var shot_started := false
var frame_no := 0
var show_noise := false
var wide := false
var alley_props: Node3D               # 巷子裡的擺設。玩家進屋後藏起來，不然會擋在鏡頭和房間中間


func _ready() -> void:
	var at := "alley"
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot="):
			shot_path = a.substr(7)
		elif a.begins_with("--shot-frames="):
			shot_after = int(a.substr(14))
		elif a.begins_with("--at="):
			at = a.substr(5)
		elif a == "--noise":
			show_noise = true
		elif a == "--wide":
			wide = true
	zh_font = SystemFont.new()
	zh_font.font_names = PackedStringArray(["Noto Sans CJK TC", "Noto Sans TC", "Microsoft JhengHei", "sans-serif"])
	Kit.setup_input()
	for i in 4:
		floor_nodes.append(_group("floor%d" % i))
	for i in 3:
		front_full.append(_group("front_full%d" % i))
		front_stub.append(_group("front_stub%d" % i))
	alley_props = _group("alley_props")
	_build_env()
	_build_stairs()          # 先建樓梯：樓板要知道洞開在哪
	_build_shell()
	_build_doors()
	_build_alley()
	_furnish()
	_build_lights()
	_build_actors()
	_build_ui()
	_spawn(at)
	_update_player()
	_apply_view(true)
	cam.position = _cam_want()


func _group(n: String) -> Node3D:
	var g := Node3D.new()
	g.name = n
	add_child(g)
	return g


func _tile(file: String) -> StandardMaterial3D:
	if not tile_cache.has(file):
		var fb: Array = TILES.get(file, [Color(0.5, 0.5, 0.5), 0])
		tile_cache[file] = Kit.tile_mat(file, fb[0], fb[1])
	return tile_cache[file]


func _room(id: String) -> Dictionary:
	for r in ROOMS:
		if r["id"] == id:
			return r
	return {}


# ------------------------------------------------------------ 環境、鏡頭
func _build_env() -> void:
	env = Kit.make_env()
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	cam = Camera3D.new()
	cam.rotation_degrees = Vector3(-22, 0, 0)
	cam.fov = 36
	if not wide:
		cam.attributes = Kit.cam_attributes()
	add_child(cam)
	cam.make_current()

	moon = DirectionalLight3D.new()                 # 冷色月光
	moon.rotation_degrees = Vector3(-42, -35, 0)
	moon.light_color = Color(0.55, 0.65, 1.0)
	moon.shadow_enabled = true
	add_child(moon)

	fill = DirectionalLight3D.new()                 # 補光：從鏡頭方向打一點中性光，角色身上的顏色才看得出來
	fill.rotation_degrees = Vector3(-25, 0, 0)
	fill.light_color = Color(1.0, 0.95, 0.88)
	fill.shadow_enabled = false
	add_child(fill)

	torch = OmniLight3D.new()
	torch.light_color = Color(1.0, 0.93, 0.8)
	torch.omni_range = 3.6
	torch.shadow_enabled = true
	add_child(torch)


func _cam_want() -> Vector3:
	if wide:
		return Vector3(0, _view_floor() * FLOOR_H + 9.7, 24.0)    # 同一個角度，拉遠到看得見整層
	return Vector3(pos.x, _ground_y() + 3.7, pos.z + 6.6)       # 和測試房間同一個角度，只是跟著人走


# ------------------------------------------------------------ 樓板、牆、屋頂
func _build_shell() -> void:
	var made := {}
	var plaster := _tile("wall_plaster")
	var outer := _tile("wall_exterior")
	var roof := _tile("roof")
	for r in ROOMS:
		var f: int = r["floor"]
		var y: float = f * FLOOR_H
		var x0: float = r["x"]
		var w: float = r["w"]
		var x1 := x0 + w
		var wall: StandardMaterial3D = _tile(r.get("wall", "wall_plaster"))
		# 樓板：一樓直接是厚的；樓上的有樓梯洞
		var thick: float = 0.2 if f == 0 else SLAB
		var holes: Array = []
		for s in stairs:
			if int(s["floor"]) + 1 == f:
				holes.append(s["rect"])
		_slab(floor_nodes[f], Rect2(x0, -D / 2, w, D), y, thick, _tile(r["tile"]), holes)
		# 後牆和左右牆。相鄰兩間共用的那面只建一次
		_wall(floor_nodes[f], f, "x", -D / 2, x0, x1, WALL_H, wall, made)
		_wall(floor_nodes[f], f, "z", x0, -D / 2, D / 2, WALL_H, wall, made)
		_wall(floor_nodes[f], f, "z", x1, -D / 2, D / 2, WALL_H, wall, made)
		# 前牆：完整的一份（從巷子看），和進屋後看到的一截矮牆
		_wall(front_full[f], f, "x", D / 2, x0, x1, WALL_H, outer, made)
		_wall(front_stub[f], f, "x", D / 2, x0, x1, 0.3, plaster, made)
		# 後牆上的窗
		for wx in r.get("win", []):
			_window(floor_nodes[f], Vector3(x0 + float(wx), y + 2.0, -D / 2 + WALL_T / 2 + 0.03), true)
		# 正面：一樓客廳和車庫另外處理，其餘每間一扇暗的窗
		if r["id"] == "garage":
			Kit.box(front_full[f], Vector3(120 * PX, 110 * PX, 0.06),
				Vector3(x0 + w / 2 + 0.5, y + 55 * PX, D / 2 + WALL_T / 2 + 0.03), _tile("shutter_front"))
		else:
			var fx: float = x0 + w / 2 + (2.0 if r["id"] == "living" else 0.0)
			_window(front_full[f], Vector3(fx, y + 2.0, D / 2 + WALL_T / 2 + 0.03), false)
		# 能走的範圍：扣掉牆的厚度和人的半徑
		walks[f].append(Rect2(x0 + WALL_T / 2 + 0.35, -D / 2 + WALL_T / 2 + 0.3, w - WALL_T - 0.7, D - WALL_T - 0.6))
		# 上面沒有房間的部分蓋屋頂。屋頂算在上一層：玩家在這層時看不到，上樓之後才看到旁邊的屋頂
		for seg in _uncovered(f + 1, x0, x1):
			var sx: float = seg.x
			var ex: float = seg.y
			Kit.box(floor_nodes[f + 1], Vector3(ex - sx + WALL_T, SLAB, D + WALL_T),
				Vector3((sx + ex) / 2, (f + 1) * FLOOR_H - SLAB / 2, 0), roof)


func _uncovered(level: int, a: float, b: float) -> Array:
	# a 到 b 這一段裡，level 那一層沒有房間蓋住的部分。回傳 Vector2(開始, 結束)
	var cuts: Array = []
	for r in ROOMS:
		if int(r["floor"]) == level:
			cuts.append(Vector2(float(r["x"]), float(r["x"]) + float(r["w"])))
	cuts.sort_custom(func(p, q): return p.x < q.x)
	var out: Array = []
	var cur := a
	for c in cuts:
		if c.y <= cur or c.x >= b:
			continue
		if c.x > cur + 0.01:
			out.append(Vector2(cur, c.x))
		cur = maxf(cur, c.y)
	if cur < b - 0.01:
		out.append(Vector2(cur, b))
	return out


func _slab(parent: Node3D, rect: Rect2, y: float, thick: float, mat: Material, holes: Array) -> void:
	# 樓板，頂面在 y。holes 裡和這塊重疊的洞（最多處理一個）會挖掉
	for h in holes:
		var hole: Rect2 = h
		if not rect.intersects(hole):
			continue
		var c := rect.intersection(hole)
		var parts := [
			Rect2(rect.position.x, rect.position.y, c.position.x - rect.position.x, rect.size.y),      # 洞的左邊
			Rect2(c.end.x, rect.position.y, rect.end.x - c.end.x, rect.size.y),                        # 洞的右邊
			Rect2(c.position.x, rect.position.y, c.size.x, c.position.y - rect.position.y),            # 洞的後面
			Rect2(c.position.x, c.end.y, c.size.x, rect.end.y - c.end.y),                              # 洞的前面
		]
		for p in parts:
			_slab(parent, p, y, thick, mat, [])
		return
	if rect.size.x < 0.01 or rect.size.y < 0.01:
		return
	Kit.box(parent, Vector3(rect.size.x, thick, rect.size.y),
		Vector3(rect.position.x + rect.size.x / 2, y - thick / 2, rect.position.y + rect.size.y / 2), mat)


func _wall(parent: Node3D, f: int, axis: String, coord: float, a: float, b: float, h: float, mat: Material, made: Dictionary) -> void:
	# axis "x"：牆沿著 x 方向（前後牆），coord 是它的 z；axis "z"：牆沿著 z 方向（左右牆），coord 是它的 x。
	var key := "%s:%d:%s:%.2f:%.2f:%.2f" % [parent.name, f, axis, coord, a, b]
	if made.has(key):
		return
	made[key] = true
	var y: float = f * FLOOR_H
	var gaps: Array = []                                    # 這面牆上的門洞：[中心, 寬, 高]
	for d in DOORS:
		if int(d["floor"]) != f or d["axis"] != axis:
			continue
		var wall_at: float = d["x"] if axis == "z" else d["z"]
		var along: float = d["z"] if axis == "z" else d["x"]
		if absf(wall_at - coord) > 0.01 or along < a or along > b:
			continue
		var px: Vector3 = d.get("px", DOOR_PX)
		gaps.append([along, px.x * PX, px.y * PX])
	gaps.sort_custom(func(p, q): return p[0] < q[0])
	var ext: float = WALL_T / 2 if axis == "x" else 0.0     # 前後牆兩頭多伸半個牆厚，把轉角補滿
	var cur := a - ext
	for g in gaps:
		var g0: float = g[0] - g[1] / 2.0
		var g1: float = g[0] + g[1] / 2.0
		_wall_piece(parent, axis, coord, cur, g0, y, h, mat)
		if h > g[2] + 0.01:
			_wall_piece(parent, axis, coord, g0, g1, y + g[2], h - g[2], mat)      # 門上面那一段
		cur = g1
	_wall_piece(parent, axis, coord, cur, b + ext, y, h, mat)


func _wall_piece(parent: Node3D, axis: String, coord: float, a: float, b: float, y: float, h: float, mat: Material) -> void:
	if b - a < 0.01:
		return
	if axis == "x":
		Kit.box(parent, Vector3(b - a, h, WALL_T), Vector3((a + b) / 2, y + h / 2, coord), mat)
	else:
		Kit.box(parent, Vector3(WALL_T, h, b - a), Vector3(coord, y + h / 2, (a + b) / 2), mat)


func _window(parent: Node3D, center: Vector3, lit: bool) -> void:
	# 窗戶：60 × 60 像素的面板。lit = 室內看出去的那種，會發冷光；不亮的是從巷子看到的暗窗
	var m := StandardMaterial3D.new()
	if ResourceLoader.exists("res://art/furniture/window.png"):
		m.albedo_texture = load("res://art/furniture/window.png")
	else:
		m.albedo_texture = Kit.pixel_tex(8, Color(0.5, 0.62, 0.95) if lit else Color(0.10, 0.13, 0.22), 0.03, 4)
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	m.roughness = 0.9
	if lit:
		m.emission_enabled = true
		m.emission = Color(0.45, 0.6, 1.0)
		m.emission_energy_multiplier = 2.2
	Kit.box(parent, Vector3(60 * PX, 60 * PX, 0.05), center, m)


# ------------------------------------------------------------ 樓梯
func _build_stairs() -> void:
	var def: Array = FURN["stair_step"]
	var filler := Kit.flat_mat(Color(0.48, 0.40, 0.32))
	var rail := Kit.flat_mat(Color(0.36, 0.28, 0.22))
	for sd in STAIRS:
		var f: int = sd["floor"]
		var dir: int = sd["dir"]
		var z0: float = sd["z"]
		var rect := Rect2(STAIR_X0, z0, STEPS * STEP_RUN, STEP_W)
		stairs.append({"id": sd["id"], "floor": f, "dir": dir, "rect": rect})
		var y: float = f * FLOOR_H
		var cz := z0 + STEP_W / 2
		for k in range(1, STEPS + 1):
			# 第 k 級：最上面是一塊階梯（有圖用圖），下面用素色方塊墊滿
			var cx: float = rect.position.x + (k - 0.5) * STEP_RUN if dir > 0 else rect.end.x - (k - 0.5) * STEP_RUN
			Kit.furniture(floor_nodes[f], "stair_step", Vector3(cx, y + (k - 1) * STEP_RISE, cz), -90.0 * dir, def[0], def[1])
			if k > 1:
				Kit.box(floor_nodes[f], Vector3(STEP_RUN, (k - 1) * STEP_RISE, STEP_W), Vector3(cx, y + (k - 1) * STEP_RISE / 2, cz), filler)
		# 樓上那個洞的欄杆：封住下樓梯口以外的三邊（貼牆的那邊不用）
		var up: Node3D = floor_nodes[f + 1]
		var ry: float = (f + 1) * FLOOR_H + 0.45
		var closed_x: float = rect.position.x if dir > 0 else rect.end.x        # 樓梯最低的那一頭，在樓上是封死的
		Kit.box(up, Vector3(0.08, 0.9, STEP_W), Vector3(closed_x, ry, cz), rail)
		Kit.box(up, Vector3(rect.size.x, 0.9, 0.08), Vector3(rect.position.x + rect.size.x / 2, ry, rect.end.y), rail)
		if z0 > -D / 2 + WALL_T:
			Kit.box(up, Vector3(rect.size.x, 0.9, 0.08), Vector3(rect.position.x + rect.size.x / 2, ry, z0), rail)


func _stair_t() -> float:
	# 在樓梯上走了多少：0 = 最下面，1 = 最上面
	var s: Dictionary = stairs[on_stair]
	var r: Rect2 = s["rect"]
	var t: float = (pos.x - r.position.x) / r.size.x
	return clampf(t if int(s["dir"]) > 0 else 1.0 - t, 0.0, 1.0)


func _ground_y() -> float:
	if on_stair >= 0:
		var s: Dictionary = stairs[on_stair]
		return int(s["floor"]) * FLOOR_H + clampi(int(_stair_t() * STEPS) + 1, 1, STEPS) * STEP_RISE
	return floor_i * FLOOR_H


func _view_floor() -> int:
	# 畫面要顯示到哪一層。上樓梯走到八成才把上面那層打開，不然人會被樓板擋住
	if on_stair >= 0:
		var s: Dictionary = stairs[on_stair]
		return int(s["floor"]) + (1 if _stair_t() > 0.8 else 0)
	return floor_i


# ------------------------------------------------------------ 門
func _build_doors() -> void:
	for d in DOORS:
		var f: int = d["floor"]
		var y: float = f * FLOOR_H
		var art: String = d.get("art", "door_interior")
		var def: Array = FURN[art]
		var px: Vector3 = d.get("px", DOOR_PX)
		var w: float = px.x * PX
		var x: float = d["x"]
		var z: float = d["z"]
		var pivot := Node3D.new()                           # 門軸。門板是一片薄板，開門就是繞著門軸轉九十度
		var bridge: Rect2                                   # 門洞裡能走的範圍，接起兩邊的房間
		if d["axis"] == "z":
			pivot.position = Vector3(x, y, z - w / 2)
			floor_nodes[f].add_child(pivot)
			Kit.furniture(pivot, art, Vector3(0, 0, w / 2), 90.0, def[0], def[1])
			bridge = Rect2(x - WALL_T / 2 - 0.36, z - w / 2 + 0.25, WALL_T + 0.72, w - 0.5)
		else:
			pivot.position = Vector3(x - w / 2, y, z)
			front_full[f].add_child(pivot)
			Kit.furniture(pivot, art, Vector3(w / 2, 0, 0), 0.0, def[0], def[1])
			bridge = Rect2(x - w / 2 + 0.25, z - WALL_T / 2 - 0.31, w - 0.5, WALL_T + 0.62)
			# 進屋後前牆只剩矮牆，門看不到，地上放一塊門墊標出門在哪
			Kit.box(floor_nodes[f], Vector3(w, 0.02, 0.6), Vector3(x, y + 0.01, z - WALL_T / 2 - 0.35), Kit.flat_mat(Color(0.45, 0.18, 0.16)))
		doors.append({
			"def": d, "pivot": pivot, "angle": 0.0, "bridge": bridge, "floor": f,
			"center": Vector2(x, z), "locked": bool(d.get("locked", false)),
		})


func _update_doors(delta: float) -> void:
	# 沒鎖的門：人走近自己開，走遠自己關。之後會改成按鍵開關（開關門有聲音，是玩法）
	for dr in doors:
		var want := 0.0
		if not dr["locked"] and int(dr["floor"]) == floor_i and on_stair < 0:
			var c: Vector2 = dr["center"]
			if Vector2(pos.x, pos.z).distance_to(c) < 1.5:
				want = 90.0
		var ang: float = move_toward(float(dr["angle"]), want, 300.0 * delta)
		dr["angle"] = ang
		var pivot: Node3D = dr["pivot"]
		pivot.rotation_degrees.y = ang


# ------------------------------------------------------------ 巷子和鄰居
func _build_alley() -> void:
	var asphalt := _tile("floor_asphalt")
	Kit.box(self, Vector3(60, 0.2, ALLEY_D + 12), Vector3(0, -0.1, D / 2 + WALL_T / 2 + (ALLEY_D + 12) / 2), asphalt)
	walks[0].append(Rect2(-ALLEY_X + 0.45, D / 2 + WALL_T / 2 + 0.3, 2 * ALLEY_X - 0.9, ALLEY_D - 0.7))
	# 兩邊的鄰居：連排透天厝，鐵捲門拉下來
	var shutter := _tile("shutter_front")
	for side in [-1, 1]:
		for i in 2:
			var w := 7.0
			var cx: float = side * (15.0 + WALL_T / 2 + w / 2 + i * w)
			var h: float = FLOOR_H * (2 if i == 0 else 3)
			Kit.box(self, Vector3(w, h, D), Vector3(cx, h / 2, 0), _tile("neighbor_a" if (i + (side + 1) / 2) % 2 == 0 else "neighbor_b"))
			Kit.box(self, Vector3(120 * PX, 110 * PX, 0.06), Vector3(cx, 55 * PX, D / 2 + 0.03), shutter)
			_window(self, Vector3(cx, FLOOR_H + 2.0, D / 2 + 0.03), false)
	# 巷子兩頭先用圍牆擋住。接上其他地區之後拿掉
	for side in [-1, 1]:
		Kit.box(self, Vector3(0.2, 1.8, ALLEY_D + 0.4), Vector3(side * ALLEY_X, 0.9, D / 2 + ALLEY_D / 2 + 0.2), _tile("wall_exterior"))


# ------------------------------------------------------------ 家具
func _furnish() -> void:
	for room_id in PLACES:
		var f := 0
		var x0 := 0.0
		var parent: Node3D = alley_props
		if room_id != "alley":
			var r := _room(room_id)
			f = r["floor"]
			x0 = r["x"]
			parent = floor_nodes[f]
		for e in PLACES[room_id]:
			var id: String = e[0]
			var yaw: float = float(e[3]) if e.size() > 3 else 0.0
			var lift: float = float(e[4]) * PX if e.size() > 4 else 0.0
			var z: float = e[2]
			if z == BACK:
				z = -D / 2 + WALL_T / 2 + 0.02 - _rear(id)
			_place(parent, f, id, Vector3(x0 + float(e[1]), f * FLOOR_H + lift, z), yaw, lift < 0.3)


func _parts(id: String) -> Array:
	return COMPOSITES.get(id, [[id, Vector3.ZERO]])


func _rear(id: String) -> float:
	# 這件家具最後面比底面中心往後多少（負的），用來貼牆
	var rear := 0.0
	for p in _parts(id):
		var off: Vector3 = p[1]
		var def: Array = FURN[p[0]]
		rear = minf(rear, off.z * PX - Kit.furniture_size(p[0], def[0]).z / 2)
	return rear


func _place(parent: Node3D, f: int, id: String, at: Vector3, yaw: float, solid: bool) -> void:
	for p in _parts(id):
		var pid: String = p[0]
		var off: Vector3 = (p[1] as Vector3) * PX
		var where_at := at + off.rotated(Vector3.UP, deg_to_rad(yaw))
		var def: Array = FURN[pid]
		if pid in STANDEES and ResourceLoader.exists("res://art/furniture/%s.png" % pid):
			Kit.prop(parent, pid, where_at)                 # 有圖的立牌不擋路
			continue
		var size := Kit.furniture(parent, pid, where_at, yaw, def[0], def[1])
		if solid and off.y < 0.01:                          # 疊在別的東西上面的不擋路
			obstacles[f].append(Kit.footprint(where_at, size, yaw))


# ------------------------------------------------------------ 燈
func _build_lights() -> void:
	for r in ROOMS:
		if r.get("dark", false):
			continue                                        # 暗的房間沒有燈
		var f: int = r["floor"]
		var l := OmniLight3D.new()
		l.position = Vector3(float(r["x"]) + float(r["w"]) / 2, f * FLOOR_H + 2.7, 0.4)
		l.light_color = r.get("light", Color(1.0, 0.80, 0.56))
		l.light_energy = 1.5
		l.omni_range = 7.0
		l.shadow_enabled = false                            # 只有玩家所在那間的燈開影子（_apply_view）
		floor_nodes[f].add_child(l)
		room_lights[r["id"]] = l
	var street := OmniLight3D.new()                         # 巷子的路燈
	street.position = Vector3(3.0, 4.1, 4.2)
	street.light_color = Color(1.0, 0.72, 0.40)
	street.light_energy = 2.2
	street.omni_range = 10.0
	street.shadow_enabled = true
	add_child(street)


# ------------------------------------------------------------ 人物
func _build_actors() -> void:
	player = Kit.sheet_actor(self, "hero", Vector3.ZERO)
	var chen := Kit.sheet_actor(floor_nodes[0], "chen", Vector3(-11.4, 0, 1.0))       # 陳水木。文字版裡他躲在床底下，這裡先站在臥室
	chen.frame_coords = Vector2i(0, 1)
	for w in [["walker", Vector2(6.0, 5.6)], ["walker_office_02", Vector2(4.6, 1.9)]]:   # 巷子一隻、廚房一隻
		var s := Kit.sheet_actor(floor_nodes[0], w[0], Vector3(w[1].x, 0, w[1].y))
		s.frame_coords = Vector2i(0, 1)
		s.flip_h = true
		walkers.append({"sprite": s, "pos": w[1], "target": NO_TARGET, "t": 0.0})
	ring = MeshInstance3D.new()                             # 聲音半徑：半徑 1 的圈，照聲音大小放大
	var tm := TorusMesh.new()
	tm.inner_radius = 0.985
	tm.outer_radius = 1.0
	ring.mesh = tm
	var rm := StandardMaterial3D.new()
	rm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	rm.albedo_color = Color(1.0, 0.85, 0.4, 0.7)
	rm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	ring.material_override = rm
	ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	ring.visible = false
	add_child(ring)


func _spawn(at: String) -> void:
	var parts := at.replace(":", ",").split(",")       # 逗號或冒號都可以（PowerShell 裡逗號要加引號）
	var id := parts[0]
	for i in stairs.size():
		if stairs[i]["id"] == id:
			var s: Dictionary = stairs[i]
			var r: Rect2 = s["rect"]
			var t: float = float(parts[1]) if parts.size() > 1 else 0.5
			on_stair = i
			floor_i = s["floor"]
			pos = Vector3(r.position.x + r.size.x * (t if int(s["dir"]) > 0 else 1.0 - t), 0, r.position.y + r.size.y / 2)
			return
	var room := _room(id)
	if not room.is_empty():
		floor_i = room["floor"]
		pos = Vector3(float(room["x"]) + float(room["w"]) / 2, 0, 1.9)
	if parts.size() > 2:
		pos.x += float(parts[1])
		pos.z += float(parts[2])


func _update_player() -> void:
	player.position = Vector3(pos.x, _ground_y() + float(player.get_meta("foot")), pos.z)
	torch.position = Vector3(pos.x, _ground_y() + 1.3, pos.z + 0.3)


# ------------------------------------------------------------ 能不能走
func _walkable(f: int, x: float, z: float) -> bool:
	var p := Vector2(x, z)
	var ok := false
	for r in walks[f]:
		if (r as Rect2).has_point(p):
			ok = true
			break
	if not ok:
		for dr in doors:
			if int(dr["floor"]) == f and not dr["locked"] and (dr["bridge"] as Rect2).has_point(p):
				ok = true
				break
	if not ok:
		return false
	for r in obstacles[f]:
		if (r as Rect2).grow(0.3).has_point(p):
			return false
	return true


func _move_ok(nx: float, nz: float) -> bool:
	# 玩家能不能走到 (nx, nz)。會順便處理上下樓梯：踏上樓梯、從樓梯兩頭走出去時換樓層
	if on_stair >= 0:
		var s: Dictionary = stairs[on_stair]
		var r: Rect2 = s["rect"]
		if nx >= r.position.x and nx <= r.end.x:
			return nz >= r.position.y + 0.3 and nz <= r.end.y - 0.3       # 在樓梯上只能沿著走
		var low_end: bool = (nx < r.position.x) == (int(s["dir"]) > 0)    # 從低的那一頭走出去
		var nf: int = int(s["floor"]) + (0 if low_end else 1)
		if _walkable(nf, nx, nz):
			floor_i = nf
			on_stair = -1
			return true
		return false
	var p := Vector2(nx, nz)
	for i in stairs.size():
		var s: Dictionary = stairs[i]
		var sf: int = s["floor"]
		if floor_i != sf and floor_i != sf + 1:
			continue                                        # 這段樓梯不在這一層
		var r: Rect2 = s["rect"]
		if not r.grow(0.3).has_point(p) or nx < r.position.x or nx > r.end.x:
			continue                                        # 離樓梯還遠，或在樓梯兩頭的外面：照一般規則
		# 要踏進樓梯的範圍：只能從對的那一頭、對的樓層。樓下從低的那頭上，樓上從高的那頭下；側面進不去
		var dir: int = s["dir"]
		var from_low: bool = pos.x < r.position.x if dir > 0 else pos.x > r.end.x
		var from_high: bool = pos.x > r.end.x if dir > 0 else pos.x < r.position.x
		if (from_low and floor_i == sf) or (from_high and floor_i == sf + 1):
			on_stair = i
			return true
		return false
	return _walkable(floor_i, nx, nz)


func _step(dir: Vector2, dist: float) -> void:
	# x、z 分開試，貼著牆和家具可以滑過去
	var nx := pos.x + dir.x * dist
	var nz := pos.z + dir.y * dist
	var was := on_stair
	if _move_ok(nx, pos.z):
		pos.x = nx
		if on_stair >= 0 and was < 0:                       # 剛踏上樓梯：站到樓梯中間那條線上
			var r: Rect2 = stairs[on_stair]["rect"]
			pos.z = clampf(pos.z, r.position.y + 0.3, r.end.y - 0.3)
	else:
		_bump(nx, pos.z)
	if _move_ok(pos.x, nz):
		pos.z = nz
	else:
		_bump(pos.x, nz)


func _bump(x: float, z: float) -> void:
	# 撞到鎖著的門：顯示訊息
	for dr in doors:
		if dr["locked"] and int(dr["floor"]) == floor_i and (dr["bridge"] as Rect2).grow(0.2).has_point(Vector2(x, z)):
			msg.text = dr["def"].get("msg", "門鎖著。")
			msg.visible = true
			msg_until = Time.get_ticks_msec() + 1800


# ------------------------------------------------------------ 顯示哪些樓層、暗不暗
func _room_at() -> Dictionary:
	if pos.z > D / 2 and floor_i == 0 and on_stair < 0:
		return {}                                           # 在巷子
	var f := _view_floor()
	for r in ROOMS:
		if int(r["floor"]) == f and pos.x >= float(r["x"]) and pos.x < float(r["x"]) + float(r["w"]):
			return r
	return {}


func _apply_view(force: bool) -> void:
	var room := _room_at()
	var inside := not room.is_empty()
	var vf := _view_floor()
	var key := "%s:%d" % [room.get("id", "alley"), vf]
	if key == last_view and not force:
		return
	last_view = key
	for i in 4:
		floor_nodes[i].visible = not inside or i <= vf      # 玩家所在樓層以上的都藏起來
	for i in 3:
		front_full[i].visible = not inside or i < vf        # 這一層的前牆換成矮牆，才看得到房間裡面
		front_stub[i].visible = inside and i == vf
	alley_props.visible = not inside
	for id in room_lights:
		(room_lights[id] as OmniLight3D).shadow_enabled = id == room.get("id", "")
	where.text = "房子骨架｜WASD 或方向鍵走，Shift 跑，點地板｜現在在：%s" % room.get("name", "巷子")


func _apply_light(delta: float, snap: bool) -> void:
	var dark: bool = _room_at().get("dark", false)
	dark_k = (1.0 if dark else 0.0) if snap else move_toward(dark_k, 1.0 if dark else 0.0, delta * 2.5)
	env.ambient_light_energy = lerpf(0.45, 0.03, dark_k)
	moon.light_energy = lerpf(0.6, 0.0, dark_k)             # 屋頂是藏起來的，暗的房間要自己把月光關掉
	fill.light_energy = lerpf(0.35, 0.03, dark_k)
	torch.light_energy = lerpf(0.0, 1.6, dark_k)
	torch.visible = dark_k > 0.01


# ------------------------------------------------------------ 行屍和聲音
func _update_walkers(delta: float, noise: float) -> void:
	# 聲音半徑裡的行屍，朝發出聲音的位置走過去。現在只算距離，不管牆，也不會繞路
	for w in walkers:
		var wp: Vector2 = w["pos"]
		if noise > 0.0 and floor_i == 0 and on_stair < 0 and wp.distance_to(Vector2(pos.x, pos.z)) <= noise:
			w["target"] = Vector2(pos.x, pos.z)
		var s: Sprite3D = w["sprite"]
		var tg: Vector2 = w["target"]
		if tg == NO_TARGET:
			continue
		var to := tg - wp
		if to.length() < 0.4:
			w["target"] = NO_TARGET
			Kit.face_walk(s, Vector2.ZERO, 0.0)
			continue
		var d := to.normalized()
		var step := WALKER_SPEED * delta
		if _walkable(0, wp.x + d.x * step, wp.y):
			wp.x += d.x * step
		if _walkable(0, wp.x, wp.y + d.y * step):
			wp.y += d.y * step
		w["pos"] = wp
		w["t"] = float(w["t"]) + delta
		s.position = Vector3(wp.x, float(s.get_meta("foot")), wp.y)
		Kit.face_walk(s, d, float(w["t"]) * 0.6)


# ------------------------------------------------------------ 介面
func _label(size: int) -> Label:
	var l := Label.new()
	l.add_theme_font_override("font", zh_font)
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_outline_color", Color.BLACK)
	l.add_theme_constant_override("outline_size", 6)
	return l


func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	info = Label.new()
	info.position = Vector2(16, 12)
	info.add_theme_font_size_override("font_size", 22)
	info.add_theme_color_override("font_outline_color", Color.BLACK)
	info.add_theme_constant_override("outline_size", 6)
	layer.add_child(info)
	where = _label(26)
	where.position = Vector2(16, 76)
	layer.add_child(where)
	msg = _label(30)
	msg.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	msg.position = Vector2(-160, -90)
	msg.visible = false
	layer.add_child(msg)


func _unhandled_input(event: InputEvent) -> void:
	# 滑鼠左鍵點地板：從鏡頭射一條線到玩家腳下那個高度的平面，走過去
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		var from := cam.project_ray_origin(event.position)
		var ray := cam.project_ray_normal(event.position)
		var gy := _ground_y()
		if ray.y < -0.001:
			var hit := from + ray * ((gy - from.y) / ray.y)
			target = Vector2(hit.x, hit.z)


func _process(delta: float) -> void:
	frame_no += 1
	if shot_path != "" and frame_no >= shot_after and not shot_started:
		shot_started = true
		Kit.take_shot(self, shot_path, frame_no)
	# 畫面上：右 = +x，下 = 朝鏡頭走（+z），上 = 往房間深處走（-z）
	var dir := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	var running := Input.is_action_pressed("run")
	if dir != Vector2.ZERO:
		target = NO_TARGET                                  # 手動操作優先，取消點地板的目標
	elif target != NO_TARGET:
		var to := target - Vector2(pos.x, pos.z)
		if to.length() < 0.1:
			target = NO_TARGET
		else:
			dir = to.normalized()
	var noise := 0.0
	if dir.length() > 0.15:
		var before := pos
		_step(dir, (RUN_SPEED if running else SPEED) * delta)
		if target != NO_TARGET and pos.is_equal_approx(before):
			target = NO_TARGET                              # 被完全擋住就停
		walk_t += delta * (1.5 if running else 1.0)
		Kit.face_walk(player, dir, walk_t)
		noise = NOISE_RUN if running else NOISE_WALK
	else:
		Kit.face_walk(player, Vector2.ZERO, walk_t)
	if show_noise:
		noise = NOISE_RUN
	_update_player()
	_update_doors(delta)
	_update_walkers(delta, noise)
	ring.visible = noise > 0.0
	if ring.visible:
		ring.position = Vector3(pos.x, _ground_y() + 0.04, pos.z)
		ring.scale = Vector3(noise, 0.3, noise)
	_apply_view(false)
	_apply_light(delta, frame_no <= 2)
	cam.position = _cam_want() if frame_no <= 2 else cam.position.lerp(_cam_want(), clampf(delta * 6.0, 0.0, 1.0))
	if msg.visible and Time.get_ticks_msec() > msg_until:
		msg.visible = false
	info.text = "ZG HD-2D house  |  %d FPS  |  %s  |  %s" % [
		Engine.get_frames_per_second(),
		RenderingServer.get_current_rendering_method(),
		RenderingServer.get_video_adapter_name(),
	]
