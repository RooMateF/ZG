extends Node3D
## ZG HD-2D 外觀測試：像素角色立在 3D 房間裡，景深 + 光暈 + 暖色檯燈 + 冷色月光。
## 這個檔是「測試房間」：一個房間，用來看美術和打光。啟動參數（寫在 -- 後面）：
##   --lineup        所有匯入的角色排成兩排
##   --panel=hero    一開始就打開人物面板
##   --shot=路徑.png [--shot-frames=30]   截圖後結束
##   --house         改跑房子模式（house.gd：住宅區第一棟透天厝的骨架），這個檔只負責把它叫起來
## 貼圖、家具、小人、輸入、截圖這些共用的工具在 kit.gd。
## 操作（PC 優先）：方向鍵、WASD 或手把左搖桿上下左右走；滑鼠點地板會走過去。
## 沒有虛擬搖桿。輸入都走 InputMap 的動作名稱，點地板在觸控螢幕上也成立，這是保留給未來移植的入口。

const Kit := preload("res://kit.gd")
const ROOM_W := 12.0
const ROOM_D := 7.0
const SPEED := 2.8
const SHEET_PIXEL := Kit.SHEET_PIXEL      # 小人一個像素多大。場景貼圖和家具用同一個密度
const NO_TARGET := Vector3(INF, INF, INF)

# 人物面板的資料。之後會改成從規則核心取，現在先寫死三個有立繪的角色。
const CAST := {
	"hero": {
		"name": "許晏", "role": "外送員　28 歲",
		"story": "在這個城市送了四年的餐。哪條巷子是死路、哪棟公寓的後門不上鎖，他比導航清楚。\n\n出事那晚他跑完最後一單，回到租屋處倒頭就睡，睡了十四個小時。醒來的時候，樓下的機車倒了一排，沒有人來扶。\n\n他沒有要救誰。他只是發現自己認得每一條路，而認得路的人，在這種時候剛好比較難死。",
	},
	"mei": {
		"name": "沈以美", "role": "藥局夜班店員　22 歲　｜　忠誠・醫療・缺藥",
		"story": "休學是為了照顧妹妹。第一個晚上，她讓妹妹以安跟著鄰居去了教堂，自己回藥局拿藥，想著拿了就走。\n\n然後街上開始有聲音。她蹲到櫃台後面，一蹲就是三天。手裡那把剪刀是剪藥袋用的。\n\n她怕得要命，但她知道櫃台後面每一個抽屜放什麼。以安在教堂咳了三天，這是她還沒有崩潰的唯一原因。",
	},
	"fujie": {
		"name": "符婕", "role": "24 歲　｜　特別登場",
		"story": "她在找她爸。\n\n她不是來加入誰的。她有自己的路要走，會來，也會走。\n\n她說話很慢，很輕，嘴角總有一點笑。她會叫你「弟弟」，不管你幾歲。",
	},
}
const CAST_ORDER := ["hero", "mei", "fujie"]

var player: Sprite3D
var lamp: OmniLight3D
var info: Label
var hud: CanvasLayer
var cam: Camera3D
var marker: MeshInstance3D         # 點地板時顯示的落點
var target := NO_TARGET            # 點地板要走去的位置
var obstacles: Array[Rect2] = []   # 地板上擋路的家具（x、z 平面）
var walk_t := 0.0
var shot_path := ""                # 截圖模式：啟動參數 -- --shot=路徑.png [--shot-frames=30]
var shot_after := 30
var frame_no := 0
var shot_started := false
var lineup := false                # 檢查模式：啟動參數 -- --lineup，所有匯入的角色排成兩排
var zh_font: SystemFont
var panel: Control                 # 人物面板（P 開關）
var panel_art: TextureRect
var panel_name: Label
var panel_role: Label
var panel_story: Label
var panel_i := 0


func _ready() -> void:
	if "--house" in OS.get_cmdline_user_args():
		# 房子模式自己管環境、鏡頭、輸入和截圖，這裡什麼都不建
		set_process(false)
		set_process_unhandled_input(false)
		add_child(load("res://house.gd").new())
		return
	var open_panel := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot="):
			shot_path = a.substr(7)
		elif a.begins_with("--shot-frames="):
			shot_after = int(a.substr(14))
		elif a.begins_with("--panel="):
			open_panel = a.substr(8)
		elif a == "--lineup":
			lineup = true
	zh_font = SystemFont.new()
	zh_font.font_names = PackedStringArray(["Noto Sans CJK TC", "Noto Sans TC", "Microsoft JhengHei", "sans-serif"])
	_build_panel.call_deferred(open_panel)
	Kit.setup_input()
	_build_env()
	_build_room()
	_build_actors()
	_build_ui()


# ------------------------------------------------------------ 環境、鏡頭
func _build_env() -> void:
	var we := WorldEnvironment.new()
	we.environment = Kit.make_env()
	add_child(we)

	cam = Camera3D.new()
	cam.position = Vector3(0, 3.7, 7.6)                      # 放低一點、抬一點頭：少拍地板，多拍房間
	cam.rotation_degrees = Vector3(-22, 0, 0)
	cam.fov = 36
	cam.attributes = Kit.cam_attributes()                    # 景深：前景和遠景都糊，中間清楚（移軸感）
	add_child(cam)
	cam.make_current()

	var moon := DirectionalLight3D.new()            # 冷色月光，從窗戶方向斜射
	moon.rotation_degrees = Vector3(-42, -35, 0)
	moon.light_color = Color(0.55, 0.65, 1.0)
	moon.light_energy = 0.7
	moon.shadow_enabled = true
	add_child(moon)

	var fill := DirectionalLight3D.new()            # 補光：從鏡頭方向打一點中性光，角色身上的顏色才看得出來
	fill.rotation_degrees = Vector3(-25, 0, 0)
	fill.light_color = Color(1.0, 0.95, 0.88)
	fill.light_energy = 0.45
	fill.shadow_enabled = false
	add_child(fill)

	lamp = OmniLight3D.new()                        # 暖色檯燈
	lamp.position = Vector3(-3.55, 1.45, -2.6)      # 電視櫃上那盞檯燈的燈罩前面
	lamp.light_color = Color(1.0, 0.72, 0.38)
	lamp.light_energy = 2.6
	lamp.omni_range = 7.0
	lamp.shadow_enabled = true
	add_child(lamp)


# ------------------------------------------------------------ 房間
func _mat(tex: ImageTexture, tile: Vector2 = Vector2.ONE, emit: Color = Color.BLACK) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_texture = tex
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST   # 像素感：不做平滑
	m.uv1_scale = Vector3(tile.x, tile.y, 1)
	m.roughness = 0.9
	if emit != Color.BLACK:
		m.emission_enabled = true
		m.emission = emit
		m.emission_energy_multiplier = 3.0
	return m


func _box(size: Vector3, pos: Vector3, mat: Material, solid: bool = false) -> MeshInstance3D:
	var mi := Kit.box(self, size, pos, mat)
	if solid:
		obstacles.append(Rect2(pos.x - size.x / 2, pos.z - size.z / 2, size.x, size.z))
	return mi


func _furniture(id: String, pos: Vector3, yaw: float = 0.0, solid: bool = true) -> Vector3:
	# 美術交的方塊家具（Kit.furniture）。pos 是底面中心。回傳寬、高、深。
	var size := Kit.furniture(self, id, pos, yaw)
	if solid and pos.y < 0.3:                                                                   # 疊在別的東西上面的不擋路
		obstacles.append(Kit.footprint(pos, size, yaw))
	return size


func _build_room() -> void:
	var floor_m := Kit.tile_mat("floor_planks")
	var wall_m := Kit.tile_mat("wall_plaster")
	var back := -ROOM_D / 2 + 0.15                                                           # 後牆的牆面

	_box(Vector3(ROOM_W, 0.2, ROOM_D), Vector3(0, -0.1, 0), floor_m)                       # 地板
	_box(Vector3(ROOM_W, 3.2, 0.3), Vector3(0, 1.6, -ROOM_D / 2), wall_m)                   # 後牆
	_box(Vector3(0.3, 3.2, ROOM_D), Vector3(-ROOM_W / 2, 1.6, 0), wall_m)                   # 左牆
	_box(Vector3(0.3, 3.2, ROOM_D), Vector3(ROOM_W / 2, 1.6, 0), wall_m)                    # 右牆
	# 家具：美術總監交的現代公寓家具（1.35 倍版，提交 4a38821），每件正面、頂面、側面各一張貼圖
	# 沙發是兩件：椅座落地，椅背疊在椅座後緣上面（底面抬高一個椅座的高度，後緣對齊）
	var seat_d: float = 40 * SHEET_PIXEL
	var seat_z := back + seat_d / 2 + 0.02
	var seat := _furniture("sofa_seat", Vector3(1.6, 0, seat_z))
	_furniture("sofa_back", Vector3(1.6, seat.y, seat_z - 15.5 * SHEET_PIXEL))
	_furniture("coffee_table", Vector3(1.6, 0, -1.2))
	var tv := _furniture("tv_console", Vector3(-3.0, 0, back + 0.32))
	Kit.prop(self, "desk_lamp", Vector3(-3.4, tv.y, back + 0.32))                                    # 檯燈放在電視櫃上
	var box := _furniture("moving_box", Vector3(3.75, 0, back + 0.33), 8.0)                 # 沙發旁邊還沒拆的紙箱
	_furniture("moving_box", Vector3(4.6, 0, back + 0.38), -12.0)
	_furniture("moving_box", Vector3(4.1, box.y, back + 0.35), 20.0)
	# 前景擺設（會被近景模糊）
	_furniture("moving_box", Vector3(4.6, 0, 2.6), 10.0)
	_furniture("moving_box", Vector3(4.55, box.y, 2.6), -14.0)
	_furniture("moving_box", Vector3(-4.9, 0, 2.9), -8.0)
	# 窗戶：會發光的冷色面板（emission，用來看光暈）
	_box(Vector3(1.8, 1.2, 0.05), Vector3(4.0, 1.9, -ROOM_D / 2 + 0.18),
		_mat(Kit.pixel_tex(8, Color(0.5, 0.62, 0.95), 0.03, 4), Vector2.ONE, Color(0.45, 0.6, 1.0)))


# ------------------------------------------------------------ 像素角色
func _sheet_actor(id: String, pos: Vector3) -> Sprite3D:
	return Kit.sheet_actor(self, id, pos)


func _build_lineup() -> void:
	# 檢查模式：所有匯入的角色正面朝鏡頭排兩排，用來比身高、看有沒有切壞。前排生存者，後排勢力代表和敵人
	var rows := [
		[1.9, 0.72, ["hero", "mei", "fujie", "qiang", "chen", "kai", "lin", "jie", "fang", "bang"]],
		[-0.6, 0.85, ["sgt", "sister", "hai", "major", "raider", "soldier", "walker", "runner", "bloater"]],
	]
	for r in rows:                                                      # 每排：z、間距、代號
		var ids: Array = r[2]
		for i in ids.size():
			var s := _sheet_actor(ids[i], Vector3((i - (ids.size() - 1) / 2.0) * r[1], 0, r[0]))
			if ids[i] == "hero":
				player = s


func _build_actors() -> void:
	if lineup:
		_build_lineup()
		return
	player = _sheet_actor("hero", Vector3(-0.6, 0, 0.9))                                           # 許晏
	var mei := _sheet_actor("mei", Vector3(-2.3, 0, -0.5))                                         # 沈以美
	mei.frame_coords = Vector2i(0, 1)
	var fujie := _sheet_actor("fujie", Vector3(1.4, 0, 0.3))                                        # 符婕
	fujie.frame_coords = Vector2i(0, 1)
	fujie.flip_h = true                                                                            # 朝左，看向許晏
	# 敵人：行屍 32 種外觀（提交 873ea5a）先放一種，加上疾走者和腫脹者（提交 4a38821）。都朝左，看向主角這邊
	for w in [["bloater", Vector3(4.2, 0, -0.9)], ["walker_police_01", Vector3(3.3, 0, 0.3)], ["runner", Vector3(2.3, 0, 1.6)]]:
		var z := _sheet_actor(w[0], w[1])
		z.frame_coords = Vector2i(0, 1)
		z.flip_h = true


# ------------------------------------------------------------ 介面
func _build_ui() -> void:
	var layer := CanvasLayer.new()
	hud = layer
	add_child(layer)
	info = Label.new()
	info.position = Vector2(16, 12)
	info.add_theme_font_size_override("font_size", 22)
	info.add_theme_color_override("font_outline_color", Color.BLACK)
	info.add_theme_constant_override("outline_size", 6)
	layer.add_child(info)
	var zh := Label.new()                               # 中文字：用系統字型
	zh.add_theme_font_override("font", zh_font)
	zh.add_theme_font_size_override("font_size", 26)
	zh.add_theme_color_override("font_outline_color", Color.BLACK)
	zh.add_theme_constant_override("outline_size", 6)
	zh.text = "末日第十四天 外觀測試｜方向鍵、WASD、手把移動，或點地板｜P 人物"
	zh.position = Vector2(16, 76)
	layer.add_child(zh)
	marker = MeshInstance3D.new()                       # 點地板的落點記號
	var disc := CylinderMesh.new()
	disc.top_radius = 0.22
	disc.bottom_radius = 0.22
	disc.height = 0.02
	marker.mesh = disc
	var mm := StandardMaterial3D.new()
	mm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mm.albedo_color = Color(1.0, 0.9, 0.5, 0.55)
	mm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	marker.material_override = mm
	marker.visible = false
	add_child(marker)


# ------------------------------------------------------------ 人物面板（立繪 + 故事）
func _zh_label(size: int, color: Color = Color.WHITE) -> Label:
	var l := Label.new()
	l.add_theme_font_override("font", zh_font)
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l


func _build_panel(open_id: String) -> void:
	var layer := CanvasLayer.new()
	layer.layer = 5
	add_child(layer)
	panel = Control.new()
	panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	panel.visible = false
	layer.add_child(panel)
	var dim := ColorRect.new()                          # 壓暗後面的場景
	dim.color = Color(0.03, 0.04, 0.07, 0.82)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	panel.add_child(dim)
	panel_art = TextureRect.new()                       # 左邊：全身立繪，保留原畫質感
	panel_art.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	panel_art.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	panel_art.anchor_left = 0.05
	panel_art.anchor_right = 0.40
	panel_art.anchor_top = 0.05
	panel_art.anchor_bottom = 0.97
	panel.add_child(panel_art)
	var box := VBoxContainer.new()                      # 右邊：名字、身分、故事
	box.anchor_left = 0.44
	box.anchor_right = 0.94
	box.anchor_top = 0.12
	box.anchor_bottom = 0.92
	box.add_theme_constant_override("separation", 14)
	panel.add_child(box)
	panel_name = _zh_label(52)
	box.add_child(panel_name)
	panel_role = _zh_label(22, Color(0.95, 0.80, 0.45))
	box.add_child(panel_role)
	var line := ColorRect.new()
	line.color = Color(1, 1, 1, 0.25)
	line.custom_minimum_size = Vector2(0, 2)
	box.add_child(line)
	panel_story = _zh_label(23, Color(0.90, 0.90, 0.92))
	panel_story.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	panel_story.size_flags_vertical = Control.SIZE_EXPAND_FILL
	box.add_child(panel_story)
	var hint := _zh_label(18, Color(1, 1, 1, 0.55))
	hint.text = "P 關閉　　← → 換人"
	box.add_child(hint)
	if open_id != "" and CAST.has(open_id):
		panel_i = CAST_ORDER.find(open_id)
		panel.visible = true
	_show_cast()


func _show_cast() -> void:
	var id: String = CAST_ORDER[panel_i]
	var c: Dictionary = CAST[id]
	panel_art.texture = load("res://art/full/%s.png" % id)
	panel_name.text = c["name"]
	panel_role.text = c["role"]
	panel_story.text = c["story"]


# ------------------------------------------------------------ 輸入
func _clear_target() -> void:
	target = NO_TARGET
	marker.visible = false


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and panel != null:
		if event.physical_keycode == KEY_P:
			panel.visible = not panel.visible
			_clear_target()
			return
		if panel.visible and event.physical_keycode in [KEY_LEFT, KEY_RIGHT, KEY_A, KEY_D]:
			var step := -1 if event.physical_keycode in [KEY_LEFT, KEY_A] else 1
			panel_i = (panel_i + step + CAST_ORDER.size()) % CAST_ORDER.size()
			_show_cast()
			return
	if panel != null and panel.visible:
		return                                           # 面板開著時不處理走路
	# 滑鼠左鍵點地板：從鏡頭射一條線到地面（y = 0），走過去。觸控螢幕的點擊也會變成這個事件。
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		var from := cam.project_ray_origin(event.position)
		var ray := cam.project_ray_normal(event.position)
		if ray.y < -0.001:
			var hit := from + ray * (-from.y / ray.y)
			target = Vector3(hit.x, 0, hit.z)
			marker.position = Vector3(hit.x, 0.02, hit.z)
			marker.visible = true


func _blocked(x: float, z: float) -> bool:
	if absf(x) > ROOM_W / 2 - 0.7 or z < -ROOM_D / 2 + 0.6 or z > ROOM_D / 2 - 0.4:
		return true
	for r in obstacles:
		if r.grow(0.35).has_point(Vector2(x, z)):
			return true
	return false


func _process(delta: float) -> void:
	frame_no += 1
	if shot_path != "" and frame_no >= shot_after and not shot_started:
		shot_started = true
		Kit.take_shot(self, shot_path, frame_no)
	# 畫面上：右 = +x，下 = 朝鏡頭走（+z），上 = 往房間深處走（-z）
	var dir := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	hud.visible = panel == null or not panel.visible       # 面板開著時收起左上角的除錯字
	if panel != null and panel.visible:
		dir = Vector2.ZERO                               # 面板開著時人不動
	if dir != Vector2.ZERO:
		_clear_target()                                  # 手動操作優先，取消點地板的目標
	elif target != NO_TARGET:
		var to := Vector2(target.x - player.position.x, target.z - player.position.z)
		if to.length() < 0.08:
			_clear_target()
		else:
			dir = to.normalized()
	if dir.length() > 0.15:
		var px := player.position.x
		var pz := player.position.z
		var nx := px + dir.x * SPEED * delta
		var nz := pz + dir.y * SPEED * delta
		if not _blocked(nx, pz):                         # x、z 分開試，貼著家具可以滑過去
			player.position.x = nx
		if not _blocked(player.position.x, nz):
			player.position.z = nz
		if target != NO_TARGET and is_equal_approx(player.position.x, px) and is_equal_approx(player.position.z, pz):
			_clear_target()                              # 被家具完全擋住就停
		walk_t += delta
		Kit.face_walk(player, dir, walk_t)
	else:
		Kit.face_walk(player, Vector2.ZERO, walk_t)
	lamp.light_energy = 2.6 + sin(Time.get_ticks_msec() * 0.011) * 0.18 + randf_range(-0.05, 0.05)   # 燈微微閃
	info.text = "ZG HD-2D look test  |  %d FPS  |  %s  |  %s\n%s" % [
		Engine.get_frames_per_second(),
		RenderingServer.get_current_rendering_method(),
		RenderingServer.get_video_adapter_name(),
		OS.get_model_name(),
	]
