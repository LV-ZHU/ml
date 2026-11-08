# 报告模板执行约定

参考文件：D:/tongji/26271/机器学习/课程项目1/机器学习-作业1-回归算法（报告模板）-2026.docx。
SHA256：4b6dccd77acfe138ec94b89c88e0ec1730d2e65c55b5b46c5f94cc1cafac1957。
参考2页、1节。证据：template.pdf、template-page-1.png、template-page-2.png、template-style.json、template-structure.txt、template-parts.json。已阅读两页完整预览。

## 版式

A4竖向，11906×16838 twips；上/下1440 twips，左/右1800 twips；单栏425 twips间隔；页眉851、页脚992 twips；无独立页眉页脚部件；行网格312 twips。保留 sectPr 原样。
正文沿用Normal样式，宋体中文和Times New Roman英文，12pt，两端对齐，首行2字；1.5倍行距。主节标题克隆源段0/10，14pt加粗居中，段前24pt、段后6pt；小节标题克隆源段1/4/7/11/14/17/20/23/26，12pt加粗左对齐，保留自动编号。正文以源段3为克隆模式，删除全部示例内容。图注及结果表新增组件采用同一字体，10.5pt，图注居中。标题使用既有Title样式并直接设为黑色，18pt。图表置于正文版心5.768英寸内。

## 填写位置

- word/document.xml/body/tbl[1]：首页贡献表，保留两列及三行成员位置。每列宽度和原有边框保持；姓名学号、贡献按用户回复填入，尚未提供时明确写待填，不编造成员。
- body/p[1..10]：一、课题综述及课题简介、课题目标、课题数据集。全部提示和House Prices示例替换为医疗费用课题。小节标题保留。
- body/p[11..28]：二、实验报告设计及2.1—2.6全部栏目。清除填写提示，以真实结果填入。图表、长正文可复制上述段落模式扩容；用显式分页维持图表与解读配对，15页内。
- body/p[29..32]：红色提交提示移除，内容在README和工作记录落实。
- 新增结尾总结和参考文献，引用真实数据与方法来源。
- 原始文件无图片、内容控件、脚注正文、超链接正文、域引用或页码域。footnotes.xml、endnotes.xml作为包部件保留。源内所有可见内容都在正文段落及唯一表格中。

## 包保留及验收

部件尺寸和SHA256见template-parts.json。仅修改document.xml、document.xml.rels和[Content_Types].xml，并添加图像部件。其余原部件保持字节不变，包括styles、numbering、settings、theme、fontTable、footnotes、endnotes、docProps和根relationships。从模板副本构建，使用python-docx完成正文对象编辑后，将不在修改白名单中的原始部件原样回填到最终ZIP。不改源模板。
保持单节及页面几何、模板标题层级、宋体12pt正文与首页贡献表。新增表格采用源表的黑色细边框、无底色，新增图表采用可读中文字。所有模板提示和示例必须清零。报告由已保存结果自动取数。
模板无Title样式。为满足文档标题要求，styles.xml仅在末尾追加Title定义；原有样式字节不变，其他部件保留规则不变。

## 渲染备选

已实际运行标准render_docx.py，缺少LibreOffice导致失败；不修改系统安装。使用本机Word只读打开、分页并导出PDF，Poppler转PNG；源与结果均走同一路径。PDF仅内部排版检查。逐页检查PNG及模板保留结构，并保存QA记录。
