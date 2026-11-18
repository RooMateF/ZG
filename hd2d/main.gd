extends Node3D
## ZG HD-2D 外觀測試：像素角色立在 3D 房間裡，景深 + 光暈 + 暖色檯燈 + 冷色月光。
## 全部用程式產生（沒有任何美術檔），只為了驗證：手機上跑不跑得動、看起來方向對不對。
## 操作（PC 優先）：方向鍵、WASD 或手把左搖桿上下左右走；滑鼠點地板會走過去。
## 沒有虛擬搖桿。輸入都走 InputMap 的動作名稱，點地板在觸控螢幕上也成立，這是保留給未來移植的入口。

const ROOM_W := 12.0
const ROOM_D := 7.0
const PIXEL := 0.075          # 一個像素在 3D 世界裡多大
const SPEED := 2.8
const NO_TARGET := Vector3(INF, INF, INF)

var player: Sprite3D
var lamp: OmniLight3D
var info: Label
var cam: Camera3D
var marker: MeshInstance3D         # 點地板時顯示的落點
var target := NO_TARGET            # 點地板要走去的位置
var obstacles: Array[Rect2] = []   # 地板上擋路的家具（x、z 平面）
var walk_t := 0.0
var frames: Array[ImageTexture] = []


func _ready() -> void:
	_setup_input()
	_build_env()
	_build_room()
	_build_actors()
	_build_ui()


# ------------------------------------------------------------ 環境、鏡頭
func _build_env() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.03, 0.04, 0.07)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.32, 0.36, 0.52)
	env.ambient_light_energy = 0.55
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.glow_enabled = true
	env.glow_intensity = 0.9
	env.glow_bloom = 0.15
	env.glow_hdr_threshold = 0.85
	env.fog_enabled = true
	env.fog_light_color = Color(0.42, 0.36, 0.32)
	env.fog_density = 0.012
	if RenderingServer.get_current_rendering_method() == "forward_plus":
		# PC 的 Forward+ 才有的效果。手機用的 Mobile 模式會跳過，畫面仍然成立（移植入口）。
		env.ssao_enabled = true
		env.ssao_intensity = 1.6
		env.volumetric_fog_enabled = true
		env.volumetric_fog_density = 0.015
		env.volumetric_fog_albedo = Color(0.9, 0.85, 0.8)
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	cam = Camera3D.new()
	cam.position = Vector3(0, 4.4, 8.2)
	cam.rotation_degrees = Vector3(-27, 0, 0)
	cam.fov = 34
	var attr := CameraAttributesPractical.new()   # 景深：前景和遠景都糊，中間清楚（移軸感）
	attr.dof_blur_far_enabled = true
	attr.dof_blur_far_distance = 10.5
	attr.dof_blur_far_transition = 3.5
	attr.dof_blur_near_enabled = true
	attr.dof_blur_near_distance = 5.0
	attr.dof_blur_near_transition = 2.0
	attr.dof_blur_amount = 0.11
	cam.attributes = attr
	add_child(cam)
	cam.make_current()

	var moon := DirectionalLight3D.new()            # 冷色月光，從窗戶方向斜射
	moon.rotation_degrees = Vector3(-42, -35, 0)
	moon.light_color = Color(0.55, 0.65, 1.0)
	moon.light_energy = 0.7
	moon.shadow_enabled = true
	add_child(moon)

	lamp = OmniLight3D.new()                        # 暖色檯燈
	lamp.position = Vector3(-3.2, 1.55, -1.8)
	lamp.light_color = Color(1.0, 0.72, 0.38)
	lamp.light_energy = 2.6
	lamp.omni_range = 7.0
	lamp.shadow_enabled = true
	add_child(lamp)


# ------------------------------------------------------------ 房間
func _pixel_tex(size: int, base: Color, vary: float, grid: int = 0) -> ImageTexture:
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(base.to_html()) + size
	for y in size:
		for x in size:
			var c := base
			var v := rng.randf_range(-vary, vary)
			c = Color(clampf(c.r + v, 0, 1), clampf(c.g + v, 0, 1), clampf(c.b + v, 0, 1))
			if grid > 0 and (x % grid == 0 or y % grid == 0):
				c = c.darkened(0.35)
			img.set_pixel(x, y, c)
	return ImageTexture.create_from_image(img)


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
	var mesh := BoxMesh.new()
	mesh.size = size
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.position = pos
	mi.material_override = mat
	add_child(mi)
	if solid:
		obstacles.append(Rect2(pos.x - size.x / 2, pos.z - size.z / 2, size.x, size.z))
	return mi


func _build_room() -> void:
	var floor_m := _mat(_pixel_tex(32, Color(0.36, 0.26, 0.18), 0.05, 16), Vector2(6, 4))
	var wall_m := _mat(_pixel_tex(32, Color(0.42, 0.40, 0.36), 0.04, 8), Vector2(8, 2))
	var wood_m := _mat(_pixel_tex(16, Color(0.30, 0.19, 0.11), 0.05, 4))
	var cloth_m := _mat(_pixel_tex(16, Color(0.24, 0.30, 0.40), 0.04))
	var crate_m := _mat(_pixel_tex(16, Color(0.45, 0.33, 0.18), 0.06, 8))

	_box(Vector3(ROOM_W, 0.2, ROOM_D), Vector3(0, -0.1, 0), floor_m)                       # 地板
	_box(Vector3(ROOM_W, 3.2, 0.3), Vector3(0, 1.6, -ROOM_D / 2), wall_m)                   # 後牆
	_box(Vector3(0.3, 3.2, ROOM_D), Vector3(-ROOM_W / 2, 1.6, 0), wall_m)                   # 左牆
	_box(Vector3(0.3, 3.2, ROOM_D), Vector3(ROOM_W / 2, 1.6, 0), wall_m)                    # 右牆
	_box(Vector3(2.6, 0.9, 1.0), Vector3(1.8, 0.45, -2.6), cloth_m, true)                   # 沙發
	_box(Vector3(2.6, 0.9, 0.3), Vector3(1.8, 1.0, -3.0), cloth_m, true)
	_box(Vector3(1.4, 0.7, 0.8), Vector3(-3.2, 0.35, -1.8), wood_m, true)                   # 桌子
	_box(Vector3(1.6, 2.4, 0.5), Vector3(-0.6, 1.2, -3.1), wood_m, true)                    # 櫃子
	_box(Vector3(1.0, 1.0, 1.0), Vector3(4.6, 0.5, 2.6), crate_m, true)                     # 前景木箱（會被近景模糊）
	_box(Vector3(0.9, 0.9, 0.9), Vector3(-4.9, 0.45, 2.9), crate_m, true)
	# 窗戶：會發光的冷色面板 + 檯燈燈泡（都是 emission，用來看光暈）
	_box(Vector3(1.8, 1.2, 0.05), Vector3(4.0, 1.9, -ROOM_D / 2 + 0.18),
		_mat(_pixel_tex(8, Color(0.5, 0.62, 0.95), 0.03, 4), Vector2.ONE, Color(0.45, 0.6, 1.0)))
	var bulb := MeshInstance3D.new()
	var sph := SphereMesh.new()
	sph.radius = 0.16
	sph.height = 0.32
	bulb.mesh = sph
	bulb.position = Vector3(-3.2, 0.95, -1.8)
	bulb.material_override = _mat(_pixel_tex(4, Color(1.0, 0.85, 0.55), 0.0), Vector2.ONE, Color(1.0, 0.75, 0.4))
	add_child(bulb)


# ------------------------------------------------------------ 像素角色（用字元畫，免美術檔）
const HERO_A := [
	"....hhhhhh....",
	"...hhhhhhhh...",
	"...hssssssh...",
	"...sskssks....",
	"...ssssssss...",
	"....ssmmss....",
	"...jjjjjjjj...",
	"..jjjjjjjjjj..",
	".sjjjjbbjjjjs.",
	".sjjjjbbjjjjs.",
	".s.jjjjjjjj.s.",
	"...pppppppp...",
	"...ppp..ppp...",
	"...ppp..ppp...",
	"...ppp..ppp...",
	"..kkkk..kkkk..",
]
const PAL := {
	"h": Color(0.22, 0.15, 0.10), "s": Color(0.93, 0.76, 0.62), "k": Color(0.10, 0.10, 0.12),
	"m": Color(0.70, 0.35, 0.32), "j": Color(0.30, 0.42, 0.34), "b": Color(0.55, 0.47, 0.30),
	"p": Color(0.20, 0.23, 0.33),
}


func _sprite_tex(rows: Array, pal: Dictionary, shift_legs: bool = false, tint: Color = Color.WHITE) -> ImageTexture:
	var h := rows.size()
	var w: int = rows[0].length()
	var img := Image.create(w, h, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	for y in h:
		var row: String = rows[y]
		for x in w:
			var ch := row[x]
			if pal.has(ch):
				var px := x
				if shift_legs and y >= h - 4:          # 走路第二格：腳錯開一個像素
					px = clampi(x + (1 if x < w / 2 else -1), 0, w - 1)
				img.set_pixel(px, y, (pal[ch] as Color) * tint)
	return ImageTexture.create_from_image(img)


func _actor(tex: ImageTexture, pos: Vector3, flip: bool = false) -> Sprite3D:
	var s := Sprite3D.new()
	s.texture = tex
	s.pixel_size = PIXEL
	s.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	s.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y      # 永遠面向鏡頭，但腳貼地
	s.shaded = true                                      # 吃場景的光
	s.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	s.flip_h = flip
	s.position = pos + Vector3(0, tex.get_height() * PIXEL * 0.5, 0)
	s.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(s)
	return s


func _build_actors() -> void:
	frames = [_sprite_tex(HERO_A, PAL), _sprite_tex(HERO_A, PAL, true)]
	player = _actor(frames[0], Vector3(-1.0, 0, 0.6))
	_actor(_sprite_tex(HERO_A, PAL, false, Color(0.62, 0.85, 0.60)), Vector3(4.2, 0, -0.8), true)   # 行屍（綠調）
	_actor(_sprite_tex(HERO_A, PAL, false, Color(1.0, 0.86, 0.86)), Vector3(-3.9, 0, -0.6))         # 生存者


# ------------------------------------------------------------ 介面
func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	info = Label.new()
	info.position = Vector2(16, 12)
	info.add_theme_font_size_override("font_size", 22)
	info.add_theme_color_override("font_outline_color", Color.BLACK)
	info.add_theme_constant_override("outline_size", 6)
	layer.add_child(info)
	var zh := Label.new()                               # 中文字測試：用系統字型
	var sf := SystemFont.new()
	sf.font_names = PackedStringArray(["Noto Sans CJK TC", "Noto Sans TC", "Microsoft JhengHei", "sans-serif"])
	zh.add_theme_font_override("font", sf)
	zh.add_theme_font_size_override("font_size", 26)
	zh.add_theme_color_override("font_outline_color", Color.BLACK)
	zh.add_theme_constant_override("outline_size", 6)
	zh.text = "末日第十四天 外觀測試｜方向鍵、WASD、手把移動，或用滑鼠點地板"
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


# ------------------------------------------------------------ 輸入
func _setup_input() -> void:
	# 動作名稱寫死、按鍵在這裡綁。之後要加別的裝置（觸控、別的手把）只改這裡。
	var binds := {
		"move_left": [[KEY_LEFT, KEY_A], JOY_AXIS_LEFT_X, -1.0],
		"move_right": [[KEY_RIGHT, KEY_D], JOY_AXIS_LEFT_X, 1.0],
		"move_up": [[KEY_UP, KEY_W], JOY_AXIS_LEFT_Y, -1.0],
		"move_down": [[KEY_DOWN, KEY_S], JOY_AXIS_LEFT_Y, 1.0],
	}
	for action in binds:
		if not InputMap.has_action(action):
			InputMap.add_action(action, 0.25)
		for k in binds[action][0]:
			var ev := InputEventKey.new()
			ev.physical_keycode = k
			InputMap.action_add_event(action, ev)
		var jm := InputEventJoypadMotion.new()
		jm.axis = binds[action][1]
		jm.axis_value = binds[action][2]
		InputMap.action_add_event(action, jm)


func _clear_target() -> void:
	target = NO_TARGET
	marker.visible = false


func _unhandled_input(event: InputEvent) -> void:
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
	# 畫面上：右 = +x，下 = 朝鏡頭走（+z），上 = 往房間深處走（-z）
	var dir := Input.get_vector("move_left", "move_right", "move_up", "move_down")
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
		if absf(dir.x) > 0.1:
			player.flip_h = dir.x < 0
		walk_t += delta
		player.texture = frames[int(walk_t * 7.0) % 2]
	else:
		player.texture = frames[0]
	lamp.light_energy = 2.6 + sin(Time.get_ticks_msec() * 0.011) * 0.18 + randf_range(-0.05, 0.05)   # 燈微微閃
	info.text = "ZG HD-2D look test  |  %d FPS  |  %s  |  %s\n%s" % [
		Engine.get_frames_per_second(),
		RenderingServer.get_current_rendering_method(),
		RenderingServer.get_video_adapter_name(),
		OS.get_model_name(),
	]
