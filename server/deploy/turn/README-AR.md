# بوابة TURN معزولة — تجربة اختيارية

TURN يساعد على تمرير ميديا الاتصال عندما يتعذر المسار المباشر. لا يوفّر تغطية
محمول ولا يثبت نجاح مكالمة برقم الشريحة. هذه الإضافة مستقلة عن PBX وOutline
وخدماتك الحالية، ولا تُثبت أو تُشغّل أي خدمة تلقائيًا.

## المصدر والإصدار

المحرك خارجي: coturn، بترخيص BSD-3-Clause. لم تُنسخ شفرته إلى المشروع.
Dockerfile يثبت حزمة Ubuntu 24.04 المحددة `coturn=4.6.1-1build4`، الموثقة في
[قائمة حزمة Ubuntu الرسمية](https://packages.ubuntu.com/noble/net/coturn).
إذا غيّرت Ubuntu الإصدار المتاح، يفشل البناء بدل تبديل الإصدار بصمت؛ راجع
تحديثات الأمان والإصدار ثم عدّل pin بمراجعة صريحة قبل الاستخدام الفعلي.
خيارات المصادقة وتقييد peers تعتمد على
[توثيق coturn الرسمي](https://github.com/coturn/coturn/wiki/turnserver)
و[مثال الإعداد الرسمي](https://github.com/coturn/coturn/blob/master/examples/etc/turnserver.conf).

## افحص خادمك أولًا

شغّل أدوات Preflight الحالية، وراجع خدمات NEXVARY وOutline وDocker والشبكات
والشهادات والموارد. يلزم منفذ TLS ‏5349/TCP ونطاق Relay ‏24000–24031/UDP،
وعنوان واجهة معتمد وشهادة موثوقة تطابق اسم TURN. لا تعدّل هذه الإضافة Firewall.
Docker يضيف قواعد شبكة ونشر منافذ عند التشغيل؛ راجع التعارضات قبل تشغيله.

الإعداد يتيح اتصال العميل عبر TLS فقط، وميديا Relay عبر UDP فقط، دون TURN TCP
relay أو STUN عام أو CLI إدارة. يستخدم حدود حصص وباندويث ومدة Allocation.
كل عناوين peers ممنوعة افتراضيًا، ثم يسمح بعناوين PBX المحددة فقط.
لا تستخدم عنوان خادم مشترك به DNS أو خدمات UDP أخرى باعتباره peer عامًا؛
coturn يقيد IP وليس منفذ peer. الأفضل عنوان PBX مخصص على شبكة معزولة.

لا يسمح المولد بـprivate أو loopback إلا مع استثناء صريح لعنوان PBX خاص تم
التحقق منه. حتى عند الاستثناء لا تُفتح شبكة كاملة: يظل السماح لعناوين IP
المحددة فقط. لا تمرر أسماء نطاقات peers قابلة للتبدل أو عناوين من طلب Android.

## توليد إعداد خاص دون تشغيل

من جذر المستودع، بعد اختيار عنوان PBX الفعلي المعتمد:

```bash
python3 server/deploy/turn/generate.py --output /private/new-turn-config \
  --realm turn.example.org --bind 127.0.0.1 \
  --relay-ip 127.0.0.1 --peer IP_OF_VERIFIED_PBX --verified-pbx
```

استبدل القيم بمعلومات حقيقية؛ `turn.example.org` ليس عنوان الخدمة. خيار
`--verified-private-peer` يجيز استثناء peer خاص أو loopback بعد التحقق فقط.
استخدم `--external-ip` لربط عنوان Relay الداخلي بعنوان NAT الخارجي الصحيح.
لا يستطيع المولد استنتاج عنوان الإنترنت أو إعداد NAT تلقائيًا.

المجلد الناتج `0700` والملفات `0600`، وفيه `auth-secret` و`turnserver.conf`؛
كلاهما يحتوي سر الخدمة ولا يُنشر أو يُرسل إلى Android أو سجل دعم. الشهادة
والمفتاح تُركّبان كملفين منفصلين للقراءة فقط. لا توجد كلمة مرور افتراضية.

## إصدار بيانات قصيرة العمر

لا يوجد endpoint عام لإصدار بيانات TURN. الأداة الإدارية تصدر بيانات المالك
المصادق عليه فقط بعد موافقته على النطاق المحدد. يجب أن يكون الملف والمجلد
مملوكين لحساب الخدمة الإداري، وبأذونات `0600` و`0700`، دون symlinks.

```bash
PYTHONPATH=server python3 -m multipath.turn \
  --secret-file /private/new-turn-config/auth-secret \
  --owner AUTHENTICATED_OWNER_ID --host turn.example.org --ttl 120 \
  --consent --output /private/owner-turn-credentials.json
```

`--owner` يأتي من هوية المالك التي تحقق منها المسؤول، لا من حقل يختاره العميل.
اسم TURN يضم وقت انتهاء وبصمة HMAC للمالك وnonce مستقلًا؛ لا يكشف هوية المالك
الأصلية. الملف الناتج يتضمن `turns:HOST:5349?transport=tcp` وusername وpassword
وexpires_at فقط، ولا يتضمن السر المشترك. مدة الصلاحية المسموحة 30–300 ثانية.
سلّم هذا الملف للمالك عبر قناة موثوقة ولا تسجله. بيانات Android تبقى في الذاكرة.

صلاحية البيانات تحدّ الدخول والمصادقة الجديدة؛ لا تعني حذف Allocation قائم
في نفس اللحظة. تضبط الخدمة عمر Allocation إلى 300 ثانية ويحتاج العميل إدارة
Refresh وتجديد بياناته بطريقة مصادق عليها. لم يُفعّل إصدار تلقائي عام أو
تكامل تجديد إنتاجي في هذه التجربة.

## تشغيل الحاوية بعد مراجعة الخطة فقط

جهّز ملف بيئة خاص يحتوي المسارات المطلقة:
`NEXVARY_TURN_CONFIG`, `NEXVARY_TURN_TLS_CERT`, `NEXVARY_TURN_TLS_KEY`، وعنوان
الربط `NEXVARY_TURN_BIND_IP`؛ الربط الافتراضي loopback. اختر subnet مستقلة
غير متعارضة في `NEXVARY_TURN_SUBNET` وIP ثابتًا داخلها في
`NEXVARY_TURN_CONTAINER_IP`. اجعل `--relay-ip` هو عنوان الحاوية الثابت الفعلي
و`--external-ip` عنوان المضيف المختار؛ لا تترك Relay على wildcard.
في إعداد الحاوية اجعل `--bind` أيضًا عنوان `NEXVARY_TURN_CONTAINER_IP` الفعلي،
حتى يستقبل coturn الاتصال المنشور على واجهة الحاوية. إبقاء `--bind 127.0.0.1`
يصلح للعملية المحلية التجريبية فقط؛ منافذ Docker لا تصل إلى loopback الحاوية.
هذا منفصل عن `NEXVARY_TURN_BIND_IP` الذي يحدد واجهة النشر على المضيف.

اجعل UID ‏10002 قادرًا على قراءة إعداد الحاوية والمفتاح الخاص بأذونات محدودة،
دون جعلهما متاحين للجميع. نسخة سر المُصدر الإداري تبقى منفصلة في مجلده الخاص.
لا تثبت Docker عشوائيًا على خادمك المشترك.

```bash
docker compose --env-file /private/turn.env -f server/deploy/turn/compose.yml config --quiet
docker compose --env-file /private/turn.env -f server/deploy/turn/compose.yml build
# تشغيل اختياري فقط بعد تحقق العزل والمنافذ والموارد والشهادة:
docker compose --env-file /private/turn.env -f server/deploy/turn/compose.yml up -d
```

الحاوية غير root، قدراتها محذوفة، filesystem للقراءة فقط، دون privileged أو
host network أو أجهزة USB. الحدود 128MB و0.5 CPU حدود تجربة غير مقيسة على
خادمك؛ لا يُضمن تحمل المستخدمين دون قياس. لا تنشر TURN للعامة قبل سياسة
وصول ومراقبة مناسبة، حتى مع وجود المصادقة.

## التحقق

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=server python3 -m unittest multipath.test_turn -v
```

يوجد اختبار شبكي حقيقي على runner مستقل بـcoturn مثبت مسبقًا:

```bash
# الجهاز التجريبي المستقل فقط؛ هذه ليست أوامر تثبيت على الخادم المشترك.
bash server/deploy/turn/ci.sh
```

يستخدم عملية coturn منفصلة وشهادة TLS موثوقة خاصة بالاختبار وpeer UDP
اصطناعيًا. يفحص رفض كلمة مرور خاطئة وبيانات منتهية على اتصال جديد، Allocation
مصادقًا، رفض peer غير مسموح، إرسال واستقبال payload عبر Relay، ثم إنهاء
Allocation. يخرج JSON منقحًا وإصدار الحزمة فقط إلى `turn-evidence/`، دون أسرار
أو شهادات خاصة أو سجلات خام. لا تعتبر الاختبار ناجحًا حتى تنتهي CI فعليًا.
هذا ليس إثبات NAT على شبكتك أو صوت Android أو مكالمة خلوية أو توافق المشغل.
