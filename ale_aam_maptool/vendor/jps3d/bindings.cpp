#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <string>
#include <vector>
#include "wrapper.h"

namespace py = pybind11;

struct JPS3DPlanResult {
  bool success{false};
  int status{4};
  std::string message;
  std::vector<std::vector<double>> path;
  double time_spent{0.0};
};

JPS3DPlanResult plan_2d_wrapper(const std::vector<float>& origin,
                                const std::vector<int>& dim,
                                const std::vector<signed char>& map_data,
                                const std::vector<float>& start,
                                const std::vector<float>& goal,
                                float resolution, bool use_jps = true) {
  JPS3DPlanResult result;
  if (origin.size() != 2 || dim.size() != 2 || start.size() != 2 || goal.size() != 2 ||
      dim[0] <= 0 || dim[1] <= 0 || resolution <= 0 ||
      map_data.size() != static_cast<size_t>(dim[0] * dim[1])) {
    result.status = 2;
    result.message = "invalid planner input";
    return result;
  }
  auto o = origin; auto d = dim; auto m = map_data; auto s = start; auto g = goal;
  result.status = plan_2d(o, d, m, s, g, resolution, result.path, result.time_spent, use_jps);
  result.success = result.status == 0 && result.path.size() >= 2;
  result.message = result.success ? "ok" : (result.status == -1 ? "no feasible path" : "native backend error");
  return result;
}

PYBIND11_MODULE(jps_planner_bindings, m) {
  m.attr("API_VERSION") = "2";
  py::class_<JPS3DPlanResult>(m, "JPS3DPlanResult")
      .def_readonly("success", &JPS3DPlanResult::success)
      .def_readonly("status", &JPS3DPlanResult::status)
      .def_readonly("message", &JPS3DPlanResult::message)
      .def_readonly("path", &JPS3DPlanResult::path)
      .def_readonly("time_spent", &JPS3DPlanResult::time_spent);
  m.def("plan_2d", &plan_2d_wrapper, py::arg("origin"), py::arg("dim"), py::arg("map_data"),
        py::arg("start"), py::arg("goal"), py::arg("resolution"), py::arg("use_jps") = true);
}
